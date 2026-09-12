"""Turn a live weather forecast into a generation forecast.

This is the middle of the pipeline. Everything upstream produces weather;
everything downstream reacts to power.

Two details are worth understanding before reading the code:

**Recursive inference.** The model uses lagged generation as a feature, and we
obviously don't know next Tuesday's generation. So we walk the horizon hour by
hour, feeding each prediction back in as the next hour's lag. That's how
operational forecasters actually do it. The alternative -- dropping lag features
-- throws away real signal, especially for wind.

**Honest backtesting.** The "yesterday's forecast vs actual" panel does NOT let
the model peek at yesterday's actuals through its lag features. We warm-start on
the day *before* yesterday and then run the same recursive loop forward with no
further ground truth, which is genuinely what we would have published 24h ago.
Feeding it real lags would make the chart look fantastic and mean nothing.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from app.core.config import MODEL_DIR
from app.services import weather_service
from app.services.tree_model import TreeEnsemble, load_ensemble
from app.services.feature_builder import FEATURE_COLUMNS, build_features
from app.services.generation_model import (
    generation_from_weather,
    solar_generation_kw,
    solar_position,
    wind_generation_kw,
)

# p10-p90. Energy forecasting quotes an 80% interval far more often than 1-sigma.
BAND_Z = 1.2816

# Uncertainty grows with lead time: a 1h-ahead forecast is a different animal
# from a 70h-ahead one. Calibrated loosely against how NWP skill decays.
HORIZON_WIDENING_PER_HOUR = 0.018
MAX_HORIZON_WIDENING = 2.4

MAX_HISTORY_HOURS = 48
BACKTEST_HOURS = 24

_model_lock = threading.Lock()


class ModelNotTrainedError(RuntimeError):
    pass


@lru_cache(maxsize=4)
def _load_model(site_type: str) -> TreeEnsemble:
    """Load the trained ensemble.

    Scored by our own numpy tree walker rather than by XGBoost: training writes
    a plain JSON model, and reading it directly keeps ~150 MB of native library
    (plus the scipy it drags in) out of the serving environment, which is what
    makes the backend fit inside a serverless bundle at all.
    `ml/verify_tree_model.py` asserts the two produce identical predictions.
    """
    path = Path(MODEL_DIR) / f"{site_type}_model.json"
    if not path.exists():
        raise ModelNotTrainedError(
            f"No trained model for '{site_type}'. Run:\n"
            "  python ml/build_historical_dataset.py\n"
            "  python ml/train_model.py"
        )
    return load_ensemble(path)


@lru_cache(maxsize=1)
def load_metrics() -> dict:
    """Training metrics, as written by ml/train_model.py."""
    import json

    path = Path(MODEL_DIR) / "metrics.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _residual_std_for(site_type: str, predicted_cf: np.ndarray) -> np.ndarray:
    """Look up the held-out residual spread for each predicted capacity factor."""
    buckets = load_metrics().get("models", {}).get(site_type, {}).get("residual_buckets", [])
    if not buckets:
        return np.full_like(predicted_cf, 0.05)

    sigma = np.full_like(predicted_cf, buckets[-1]["residual_std"])
    for bucket in buckets:
        mask = (predicted_cf >= bucket["cf_low"]) & (predicted_cf < bucket["cf_high"])
        sigma[mask] = bucket["residual_std"]
    return sigma


def _predict_recursive(
    site,
    weather: pd.DataFrame,
    known_generation: pd.Series | None,
) -> pd.Series:
    """Walk the horizon hour by hour, feeding each prediction back in as a lag.

    Hours present in `known_generation` are treated as ground truth for the lag
    features (that's the warm start); everything else is predicted and then used
    to seed the hour after it.
    """
    model = _load_model(site.site_type)
    capacity = float(site.capacity_kw)

    features = build_features(
        weather,
        capacity_kw=capacity,
        latitude=site.latitude,
        longitude=site.longitude,
        generation_kw=None,
    )
    static = features[[c for c in FEATURE_COLUMNS if not c.startswith(("lag_cf", "roll_cf"))]]
    static_matrix = static.to_numpy(dtype="float32")
    static_names = list(static.columns)

    lag_1_idx = FEATURE_COLUMNS.index("lag_cf_1h")
    lag_3_idx = FEATURE_COLUMNS.index("lag_cf_3h")
    roll_idx = FEATURE_COLUMNS.index("roll_cf_24h")
    static_positions = [FEATURE_COLUMNS.index(name) for name in static_names]

    known_cf: dict[pd.Timestamp, float] = {}
    if known_generation is not None:
        for stamp, value in (known_generation / capacity).clip(0.0, 1.0).items():
            known_cf[stamp] = float(value)

    n = len(weather)
    cf_trace = np.zeros(n)  # what we believe happened/will happen, used for lags
    predicted = np.zeros(n)
    row = np.zeros((1, len(FEATURE_COLUMNS)), dtype="float32")

    # A sensible cold-start value so the very first hours aren't predicted off zeros.
    seed_cf = float(np.mean(list(known_cf.values()))) if known_cf else 0.0

    with _model_lock:
        for i in range(n):
            row[0, static_positions] = static_matrix[i]
            row[0, lag_1_idx] = cf_trace[i - 1] if i >= 1 else seed_cf
            row[0, lag_3_idx] = cf_trace[i - 3] if i >= 3 else seed_cf
            window = cf_trace[max(0, i - 24) : i]
            row[0, roll_idx] = float(window.mean()) if len(window) >= 3 else seed_cf

            predicted[i] = float(np.clip(model.predict(row)[0], 0.0, 1.0))

            stamp = weather.index[i]
            cf_trace[i] = known_cf.get(stamp, predicted[i])

    return pd.Series(predicted * capacity, index=weather.index, name="predicted_kw")


def _potential_kw(site, weather: pd.DataFrame) -> pd.Series:
    """What the site could produce under clear skies / its own wind regime.

    For solar this is the clear-sky ceiling, which is what separates "it's dusk"
    from "a cloud bank just parked over the array". For wind there is no
    equivalent ceiling, so we use the physics curve on the forecast wind itself.
    """
    if site.site_type == "solar":
        geometry = solar_position(weather.index, site.latitude, site.longitude)
        values = solar_generation_kw(
            site.capacity_kw, geometry["clear_sky_ghi"], weather["temperature_2m"]
        )
    else:
        values = wind_generation_kw(site.capacity_kw, weather["windspeed_100m"])
    return pd.Series(values, index=weather.index, name="potential_kw")


def _weather_records(weather: pd.DataFrame) -> list[dict]:
    return [
        {
            "ghi_wm2": round(float(r["shortwave_radiation"]), 1),
            "direct_radiation_wm2": round(float(r["direct_radiation"]), 1),
            "diffuse_radiation_wm2": round(float(r["diffuse_radiation"]), 1),
            "temperature_c": round(float(r["temperature_2m"]), 1),
            "windspeed_10m_ms": round(float(r["windspeed_10m"]), 2),
            "windspeed_100m_ms": round(float(r["windspeed_100m"]), 2),
            "cloudcover_pct": round(float(r["cloudcover"]), 1),
        }
        for _, r in weather.iterrows()
    ]


def prefetch_weather(sites, horizon_hours: int = 72) -> None:
    """Warm the weather cache for several sites at once.

    Building a portfolio means one Open-Meteo round trip per site, and done in
    sequence that is most of the wall time on a cold cache. The calls are
    independent and almost entirely network wait, so a small thread pool
    collapses them into roughly the cost of the slowest one.

    This only populates `weather_service`'s cache -- the forecasts themselves
    are still built one at a time afterwards, which keeps the database session
    single-threaded. Failures are ignored on purpose: a site whose prefetch
    fails simply pays for its own fetch later, or surfaces its error there.
    """
    forecast_days = int(np.ceil(int(np.clip(horizon_hours, 1, 72)) / 24)) + 1

    def _warm(site) -> None:
        try:
            weather_service.fetch_forecast(
                site.latitude, site.longitude, forecast_days=forecast_days, past_days=2
            )
        except Exception:
            pass

    sites = list(sites)
    if len(sites) < 2:
        return
    with ThreadPoolExecutor(max_workers=min(len(sites), 8)) as pool:
        list(pool.map(_warm, sites))


def build_site_forecast(site, horizon_hours: int = 72) -> dict:
    """The full forecast payload for one site: history, forward forecast, bands.

    Everything the alert engine, the recommendation engine and the dashboard
    need comes out of this one call, so a page render costs one Open-Meteo
    request at most (and usually zero, thanks to the cache).
    """
    horizon_hours = int(np.clip(horizon_hours, 1, 72))
    forecast_days = int(np.ceil(horizon_hours / 24)) + 1
    weather = weather_service.fetch_forecast(
        site.latitude, site.longitude, forecast_days=forecast_days, past_days=2
    )

    now = pd.Timestamp.now(tz="UTC").floor("h")
    # "Modelled actual": real observed weather run through the physics model.
    # It stands in for the SCADA feed a utility would wire in here.
    actual_kw = generation_from_weather(
        site.site_type,
        site.capacity_kw,
        weather.loc[weather.index <= now],
        add_noise=True,
        seed=site.id * 101,
    )

    past_index = weather.index[weather.index <= now]
    future_index = weather.index[weather.index > now][:horizon_hours]

    # --- Forward forecast: warm-start on everything we know, then run out. ----
    forward_window = weather.loc[weather.index <= future_index[-1]] if len(future_index) else weather
    forward_pred = _predict_recursive(site, forward_window, known_generation=actual_kw)

    # --- Backtest: what we would have published 24h ago, no peeking. ----------
    backtest = pd.Series(dtype=float)
    cutoff = now - pd.Timedelta(hours=BACKTEST_HOURS)
    if len(past_index) and past_index[0] <= cutoff:
        warm = actual_kw.loc[actual_kw.index <= cutoff]
        backtest_window = weather.loc[weather.index <= now]
        backtest = _predict_recursive(site, backtest_window, known_generation=warm)
        backtest = backtest.loc[backtest.index > cutoff]

    potential = _potential_kw(site, weather)

    # Trees extrapolate a little sloppily near zero and will happily emit a few
    # hundred kW of solar at 2am. Physics says otherwise: no sun above the
    # horizon, or wind below cut-in, means exactly zero. Real forecasters apply
    # the same clamp, and without it the chart has a visible fake baseline.
    forward_pred = forward_pred.where(potential.reindex(forward_pred.index) > 0.0, 0.0)
    if not backtest.empty:
        backtest = backtest.where(potential.reindex(backtest.index) > 0.0, 0.0)

    sigma_cf = _residual_std_for(site.site_type, (forward_pred / site.capacity_kw).to_numpy())
    sigma = pd.Series(sigma_cf * site.capacity_kw, index=forward_pred.index)

    # --- Assemble the forward rows -------------------------------------------
    forecast_rows = []
    future_weather = weather.loc[future_index]
    future_weather_records = _weather_records(future_weather)
    for lead, (stamp, wrec) in enumerate(zip(future_index, future_weather_records), start=1):
        predicted = float(forward_pred.loc[stamp])
        widening = min(1.0 + HORIZON_WIDENING_PER_HOUR * lead, MAX_HORIZON_WIDENING)
        # A hard physical zero has no uncertainty around it either.
        half_band = 0.0 if predicted <= 0.0 else float(sigma.loc[stamp]) * BAND_Z * widening
        forecast_rows.append(
            {
                "timestamp": stamp.isoformat(),
                "hours_ahead": lead,
                "predicted_kw": round(predicted, 1),
                "lower_kw": round(max(predicted - half_band, 0.0), 1),
                "upper_kw": round(min(predicted + half_band, site.capacity_kw), 1),
                "capacity_factor": round(predicted / site.capacity_kw, 4),
                "potential_kw": round(float(potential.loc[stamp]), 1),
                "weather": wrec,
            }
        )

    # --- Assemble the history rows (actual vs. the day-ahead backtest) --------
    history_index = past_index[-MAX_HISTORY_HOURS:]
    history_rows = []
    for stamp in history_index:
        row = {
            "timestamp": stamp.isoformat(),
            "actual_kw": round(float(actual_kw.loc[stamp]), 1),
            "predicted_kw": None,
        }
        if stamp in backtest.index:
            row["predicted_kw"] = round(float(backtest.loc[stamp]), 1)
        history_rows.append(row)

    metrics = load_metrics().get("models", {}).get(site.site_type, {})
    band_pct = (
        float(np.mean([r["upper_kw"] - r["lower_kw"] for r in forecast_rows[:24]]))
        / site.capacity_kw
        * 100
        if forecast_rows
        else 0.0
    )

    return {
        "site_id": site.id,
        "site_name": site.name,
        "site_type": site.site_type,
        "capacity_kw": site.capacity_kw,
        "export_limit_kw": site.effective_export_limit_kw,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon_hours": len(forecast_rows),
        "current": {
            "timestamp": now.isoformat(),
            "output_kw": round(float(actual_kw.iloc[-1]), 1) if len(actual_kw) else 0.0,
            "capacity_factor": round(float(actual_kw.iloc[-1]) / site.capacity_kw, 4)
            if len(actual_kw)
            else 0.0,
            "weather": weather_service.current_conditions(weather),
        },
        "today_generated_kwh": round(
            float(actual_kw.loc[actual_kw.index >= now.normalize()].sum()), 1
        ),
        "forecast": forecast_rows,
        "history": history_rows,
        "backtest": _backtest_accuracy(actual_kw, backtest, site.capacity_kw),
        "model": {
            "algorithm": "XGBoost gradient-boosted trees",
            "trained_at": load_metrics().get("trained_at"),
            "mae_pct_capacity": metrics.get("mae_pct_capacity"),
            "rmse_pct_capacity": metrics.get("rmse_pct_capacity"),
            "r2": metrics.get("r2"),
            "improvement_over_persistence_pct": metrics.get("improvement_over_persistence_pct"),
            # Mean p10-p90 band width over the next 24h, inverted so it reads as
            # a confidence figure. Narrow band => the model is sure.
            "confidence_pct": round(max(0.0, 100.0 - band_pct), 1),
            "band_width_pct_capacity": round(band_pct, 2),
        },
    }


def _backtest_accuracy(actual: pd.Series, predicted: pd.Series, capacity: float) -> dict:
    """Score the last 24h of day-ahead forecast against what actually happened."""
    if predicted.empty:
        return {"available": False}

    joined = pd.concat([actual.rename("actual"), predicted.rename("predicted")], axis=1).dropna()
    if joined.empty:
        return {"available": False}

    error = joined["actual"] - joined["predicted"]
    return {
        "available": True,
        "hours_scored": int(len(joined)),
        "mae_kw": round(float(error.abs().mean()), 1),
        "mae_pct_capacity": round(float(error.abs().mean()) / capacity * 100, 2),
        "bias_kw": round(float(error.mean()), 1),
        "window_start": joined.index.min().isoformat(),
        "window_end": joined.index.max().isoformat(),
    }


def rolling_backtest(site, days: int = 7) -> dict:
    """Replay the last `days` days one day at a time and score the result.

    This is a rolling-origin evaluation, not a single hindcast. For each day we
    rewind to that morning, hand the model only what it would have known then,
    and let it run 24h forward unaided. Stitching those runs together gives an
    honest picture of day-ahead performance over a week -- the same procedure a
    utility would use to decide whether to trust a vendor's forecast.
    """
    days = int(np.clip(days, 1, 10))
    weather = weather_service.fetch_forecast(
        site.latitude, site.longitude, forecast_days=1, past_days=days + 2
    )
    now = pd.Timestamp.now(tz="UTC").floor("h")
    past = weather.loc[weather.index <= now]
    actual = generation_from_weather(
        site.site_type, site.capacity_kw, past, add_noise=True, seed=site.id * 101
    )
    potential = _potential_kw(site, past)

    stitched: dict[pd.Timestamp, float] = {}
    for day_back in range(days, 0, -1):
        origin = now - pd.Timedelta(hours=24 * day_back)
        if origin <= past.index[0]:
            continue
        warm = actual.loc[actual.index <= origin]
        if warm.empty:
            continue
        window = past.loc[past.index <= origin + pd.Timedelta(hours=24)]
        predicted = _predict_recursive(site, window, known_generation=warm)
        predicted = predicted.loc[predicted.index > origin]
        for stamp, value in predicted.items():
            stitched[stamp] = float(value)

    rows = []
    for stamp in past.index:
        if stamp not in stitched:
            continue
        prediction = stitched[stamp] if potential.loc[stamp] > 0 else 0.0
        rows.append(
            {
                "timestamp": stamp.isoformat(),
                "actual_kw": round(float(actual.loc[stamp]), 1),
                "predicted_kw": round(prediction, 1),
            }
        )

    return {
        "site_id": site.id,
        "site_name": site.name,
        "days": days,
        "capacity_kw": site.capacity_kw,
        "points": rows,
        "accuracy": _score(rows, site.capacity_kw),
    }


def _score(rows: list[dict], capacity: float) -> dict:
    """MAE / RMSE / R2 over a stitched backtest, quoted as % of capacity."""
    if not rows:
        return {"available": False}

    actual = np.array([r["actual_kw"] for r in rows], dtype=float)
    predicted = np.array([r["predicted_kw"] for r in rows], dtype=float)
    error = actual - predicted
    variance = float(np.sum((actual - actual.mean()) ** 2))

    return {
        "available": True,
        "hours_scored": len(rows),
        "mae_kw": round(float(np.mean(np.abs(error))), 1),
        "mae_pct_capacity": round(float(np.mean(np.abs(error))) / capacity * 100, 2),
        "rmse_kw": round(float(np.sqrt(np.mean(error**2))), 1),
        "rmse_pct_capacity": round(float(np.sqrt(np.mean(error**2))) / capacity * 100, 2),
        # Guard the degenerate case: a site that sat at zero all week has no
        # variance to explain, and R2 would be meaningless rather than perfect.
        "r2": round(1.0 - float(np.sum(error**2)) / variance, 4) if variance > 0 else None,
        "bias_kw": round(float(np.mean(error)), 1),
    }
