"""One feature set, built the same way for training and for live inference.

Train/serve skew is the classic way an ML demo falls over in front of judges, so
both paths call `build_features` here rather than each rolling their own.

Note the target: we learn *capacity factor* (output / nameplate), not raw kW.
That lets one solar model serve a 10 MW rooftop and a 180 MW park, and it makes
the headline error metric directly interpretable — MAE in capacity-factor points
is MAE as a percentage of capacity, which is how the industry quotes it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.generation_model import solar_position

# Order matters: XGBoost is fed a plain matrix, so training and inference must
# present columns in exactly this sequence.
FEATURE_COLUMNS = [
    "hour_sin",
    "hour_cos",
    "doy_sin",
    "doy_cos",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
    "cloudcover",
    "temperature_2m",
    "windspeed_10m",
    "windspeed_100m",
    "wind_shear",
    "solar_elevation_deg",
    "clear_sky_ghi",
    "clear_sky_index",
    "capacity_kw",
    "latitude",
    "lag_cf_1h",
    "lag_cf_3h",
    "roll_cf_24h",
]

TARGET_COLUMN = "capacity_factor"


def build_features(
    weather: pd.DataFrame,
    *,
    capacity_kw: float,
    latitude: float,
    longitude: float,
    generation_kw: pd.Series | None = None,
) -> pd.DataFrame:
    """Turn a weather frame into the model's feature matrix.

    Pass `generation_kw` when you have it (training, or the warm-start window at
    inference) and the lag columns get filled from it. Leave it out and the lag
    columns arrive as NaN for the caller to fill in recursively.
    """
    frame = weather.copy()
    index = frame.index

    # Cyclical encoding: hour 23 and hour 0 should sit next to each other, which
    # a raw 0-23 integer can't express.
    hour = index.hour.to_numpy(dtype=float)
    doy = index.dayofyear.to_numpy(dtype=float)
    frame["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    frame["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    frame["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    frame["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)

    # Ratio of hub-height to 10m wind — a proxy for atmospheric stability, which
    # is what makes an evening wind ramp behave differently from a midday one.
    frame["wind_shear"] = frame["windspeed_100m"] / np.maximum(frame["windspeed_10m"], 0.1)

    geometry = solar_position(index, latitude, longitude)
    frame["solar_elevation_deg"] = geometry["solar_elevation_deg"]
    frame["clear_sky_ghi"] = geometry["clear_sky_ghi"]
    frame["clear_sky_index"] = frame["shortwave_radiation"] / np.maximum(frame["clear_sky_ghi"], 1.0)
    frame["clear_sky_index"] = frame["clear_sky_index"].clip(0.0, 1.3)

    frame["capacity_kw"] = float(capacity_kw)
    frame["latitude"] = float(latitude)

    if generation_kw is not None:
        cf = (generation_kw / float(capacity_kw)).clip(0.0, 1.0)
        frame[TARGET_COLUMN] = cf
        frame["lag_cf_1h"] = cf.shift(1)
        frame["lag_cf_3h"] = cf.shift(3)
        # min_periods keeps the first day of history usable instead of dropping it.
        frame["roll_cf_24h"] = cf.shift(1).rolling(24, min_periods=3).mean()
    else:
        frame["lag_cf_1h"] = np.nan
        frame["lag_cf_3h"] = np.nan
        frame["roll_cf_24h"] = np.nan

    return frame


def feature_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    """Select the model's columns, in the fixed order, as float32."""
    return frame[FEATURE_COLUMNS].astype("float32")
