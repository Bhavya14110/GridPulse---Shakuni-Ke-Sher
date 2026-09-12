"""Open-Meteo client.

Two endpoints matter to us:

* the *forecast* API, which gives us the same NWP output a utility's own weather
  desk would see — that's what we convert into a power forecast at request time;
* the *archive* API (ERA5 reanalysis), which we replay through the physics model
  to manufacture a weather-correlated historical generation record to train on.

No API key, no signup, no rate-limit dance. We keep a small in-process TTL cache
so a page that asks for weather, forecast and alerts doesn't trigger three calls.
"""
from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests

from app.core.config import settings

# Everything the physics model and the ML feature set need, in one request.
HOURLY_VARS = [
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
    "temperature_2m",
    "windspeed_10m",
    "windspeed_100m",
    "cloudcover",
]

# ERA5 reanalysis lands roughly five days behind real time; ask for anything
# newer and the tail of the response is nulls.
ARCHIVE_LAG_DAYS = 6

_cache: dict[tuple, tuple[float, pd.DataFrame]] = {}
_cache_lock = threading.Lock()


class WeatherError(RuntimeError):
    """Raised when Open-Meteo is unreachable or hands back something unusable."""


def _get_json(url: str, params: dict, attempts: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, params=params, timeout=25)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # network blip, 5xx, malformed JSON
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))
    raise WeatherError(f"Open-Meteo request failed after {attempts} attempts: {last_error}")


def _to_frame(payload: dict) -> pd.DataFrame:
    hourly = payload.get("hourly")
    if not hourly or not hourly.get("time"):
        raise WeatherError("Open-Meteo returned no hourly block")

    frame = pd.DataFrame(hourly)
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame = frame.set_index("time").sort_index()

    # ERA5 occasionally has gaps at the very edge of the window; interpolating
    # across a couple of hours is far better than dropping the rows, because the
    # lag features downstream assume a contiguous hourly index.
    for column in HOURLY_VARS:
        if column not in frame.columns:
            frame[column] = 0.0
    frame[HOURLY_VARS] = (
        frame[HOURLY_VARS].astype(float).interpolate(limit_direction="both").fillna(0.0)
    )
    return frame[HOURLY_VARS]


def _cached(key: tuple, ttl_seconds: int, producer) -> pd.DataFrame:
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl_seconds:
            return hit[1].copy()
    frame = producer()
    with _cache_lock:
        _cache[key] = (now, frame)
    return frame.copy()


def fetch_forecast(
    latitude: float,
    longitude: float,
    forecast_days: int = 4,
    past_days: int = 2,
) -> pd.DataFrame:
    """Hourly weather from `past_days` ago through `forecast_days` ahead, in UTC.

    We deliberately ask for past days in the *same* call: those hours warm-start
    the model's lag features and power the "yesterday's forecast vs actual" view,
    at no extra request cost.
    """

    def _producer() -> pd.DataFrame:
        payload = _get_json(
            settings.forecast_api,
            {
                "latitude": round(latitude, 4),
                "longitude": round(longitude, 4),
                "hourly": ",".join(HOURLY_VARS),
                "forecast_days": forecast_days,
                "past_days": past_days,
                "timezone": "UTC",
                "windspeed_unit": "ms",
            },
        )
        return _to_frame(payload)

    key = ("forecast", round(latitude, 3), round(longitude, 3), forecast_days, past_days)
    return _cached(key, settings.cache_ttl_minutes * 60, _producer)


def fetch_archive(latitude: float, longitude: float, start: date, end: date) -> pd.DataFrame:
    """Hourly ERA5 reanalysis weather for a closed [start, end] date range, in UTC."""

    def _producer() -> pd.DataFrame:
        payload = _get_json(
            settings.archive_api,
            {
                "latitude": round(latitude, 4),
                "longitude": round(longitude, 4),
                "hourly": ",".join(HOURLY_VARS),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "timezone": "UTC",
                "windspeed_unit": "ms",
            },
        )
        return _to_frame(payload)

    key = ("archive", round(latitude, 3), round(longitude, 3), start, end)
    return _cached(key, 24 * 3600, _producer)


def archive_window(months: int) -> tuple[date, date]:
    """The most recent `months`-long window that ERA5 has actually published."""
    end = datetime.now(timezone.utc).date() - timedelta(days=ARCHIVE_LAG_DAYS)
    start = end - timedelta(days=int(months * 30.44))
    return start, end


def current_conditions(frame: pd.DataFrame) -> dict:
    """Pick the row closest to 'now' out of a forecast frame, as plain floats."""
    now = pd.Timestamp.now(tz="UTC").floor("h")
    if now not in frame.index:
        now = frame.index[frame.index.get_indexer([now], method="nearest")[0]]
    row = frame.loc[now]
    return {
        "timestamp": now.isoformat(),
        "ghi_wm2": float(row["shortwave_radiation"]),
        "direct_radiation_wm2": float(row["direct_radiation"]),
        "diffuse_radiation_wm2": float(row["diffuse_radiation"]),
        "temperature_c": float(row["temperature_2m"]),
        "windspeed_10m_ms": float(row["windspeed_10m"]),
        "windspeed_100m_ms": float(row["windspeed_100m"]),
        "cloudcover_pct": float(row["cloudcover"]),
    }
