"""Physics-informed generation model.

This is the bridge between weather and power. It does two jobs:

1. It manufactures the "historical generation record" the problem statement asks
   for — we replay real ERA5 weather through these formulas to get a plausible,
   weather-correlated generation history to train the ML model on. Nobody hands
   out utility SCADA data during a hackathon, and inventing random numbers would
   teach the model nothing.
2. It gives us a physics baseline to sanity-check the ML forecast against.

The formulas are the standard first-order ones used for yield estimation: a
performance-ratio + temperature-derate model for PV, and a piecewise turbine
power curve for wind.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# --- PV constants -----------------------------------------------------------
STC_IRRADIANCE = 1000.0  # W/m^2, the irradiance panels are rated at
PERFORMANCE_RATIO = 0.78  # soiling, wiring, inverter, mismatch losses rolled up
TEMP_COEFF_PER_C = 0.004  # ~0.4% output lost per degree above 25C
TEMP_REF_C = 25.0
# Cells run hotter than the air around them; roughly +0.03C per W/m^2 of sun.
CELL_TEMP_RISE_PER_WM2 = 0.03

# --- Turbine power curve constants ------------------------------------------
CUT_IN_MS = 3.5
RATED_MS = 12.5
CUT_OUT_MS = 25.0


def solar_generation_kw(
    capacity_kw: float,
    ghi_wm2: np.ndarray | pd.Series,
    temperature_c: np.ndarray | pd.Series,
) -> np.ndarray:
    """PV output from global horizontal irradiance and ambient temperature."""
    ghi = np.asarray(ghi_wm2, dtype=float)
    ambient = np.asarray(temperature_c, dtype=float)

    cell_temp = ambient + CELL_TEMP_RISE_PER_WM2 * ghi
    # Above 25C the module loses efficiency; below it, it gains a little, which
    # is why cold clear days out-produce hot ones at the same irradiance.
    derate = 1.0 - TEMP_COEFF_PER_C * (cell_temp - TEMP_REF_C)
    derate = np.clip(derate, 0.6, 1.05)

    output = capacity_kw * (ghi / STC_IRRADIANCE) * PERFORMANCE_RATIO * derate
    return np.clip(output, 0.0, capacity_kw)


def wind_generation_kw(capacity_kw: float, windspeed_100m_ms: np.ndarray | pd.Series) -> np.ndarray:
    """Standard four-region turbine power curve, fed hub-height (100m) wind speed.

    Below cut-in the rotor can't overcome its own losses; between cut-in and
    rated the power in the wind scales with v^3; above rated the turbine pitches
    to hold nameplate; above cut-out it shuts down to protect itself. That last
    region is why a storm can take a wind farm to zero — worth flagging to a
    grid operator, which is exactly what the ramp rule downstream catches.
    """
    wind = np.asarray(windspeed_100m_ms, dtype=float)
    output = np.zeros_like(wind)

    ramp = (wind >= CUT_IN_MS) & (wind < RATED_MS)
    # Normalised cubic interpolation between cut-in and rated.
    output[ramp] = capacity_kw * (
        (wind[ramp] ** 3 - CUT_IN_MS**3) / (RATED_MS**3 - CUT_IN_MS**3)
    )

    rated = (wind >= RATED_MS) & (wind <= CUT_OUT_MS)
    output[rated] = capacity_kw

    return np.clip(output, 0.0, capacity_kw)


def apply_realism_noise(
    values: np.ndarray,
    capacity_kw: float,
    noise_pct: float = 0.06,
    seed: int | None = None,
) -> np.ndarray:
    """Add the wobble real assets have — inverter clipping, wake effects, dust.

    Noise is proportional to output, with a small absolute floor so the model
    can't learn a noise-free mapping and report a fake-looking R^2 of 0.999.
    Hours where the physics says zero stay exactly zero — a dark panel and a
    parked turbine don't jitter, and letting them would put fake generation on
    the chart at midnight.
    """
    rng = np.random.default_rng(seed)
    scale = noise_pct * np.maximum(values, 0.02 * capacity_kw)
    noisy = np.where(values > 0.0, values + rng.normal(0.0, scale), 0.0)
    return np.clip(noisy, 0.0, capacity_kw)


def generation_from_weather(
    site_type: str,
    capacity_kw: float,
    weather: pd.DataFrame,
    add_noise: bool = True,
    seed: int | None = None,
) -> pd.Series:
    """Run a whole weather frame through the right physics model."""
    if site_type == "solar":
        values = solar_generation_kw(
            capacity_kw, weather["shortwave_radiation"], weather["temperature_2m"]
        )
    elif site_type == "wind":
        values = wind_generation_kw(capacity_kw, weather["windspeed_100m"])
    else:
        raise ValueError(f"Unknown site type: {site_type!r}")

    if add_noise:
        values = apply_realism_noise(values, capacity_kw, seed=seed)

    return pd.Series(values, index=weather.index, name="generation_kw")


# --- Solar geometry ---------------------------------------------------------
# Pure astronomy: no data source needed, just latitude/longitude and the clock.
# Sun elevation is a strong ML feature (it tells the model *why* irradiance is
# low — dusk vs. cloud) and it defines the "typical high-generation window" the
# under-generation rule needs, without us having to hardcode 9am-4pm anywhere.


def solar_position(index: pd.DatetimeIndex, latitude: float, longitude: float) -> pd.DataFrame:
    """Sun elevation (degrees) and clear-sky GHI (W/m^2) for each UTC timestamp.

    NOAA's low-precision solar position algorithm — good to a fraction of a
    degree, which is far more than we need to know whether the sun is up.
    """
    day_of_year = index.dayofyear.to_numpy(dtype=float)
    utc_hour = index.hour.to_numpy(dtype=float) + index.minute.to_numpy(dtype=float) / 60.0

    fractional_year = 2.0 * np.pi / 365.0 * (day_of_year - 1.0 + (utc_hour - 12.0) / 24.0)

    # Equation of time (minutes) corrects clock time to actual solar time.
    eq_time = 229.18 * (
        0.000075
        + 0.001868 * np.cos(fractional_year)
        - 0.032077 * np.sin(fractional_year)
        - 0.014615 * np.cos(2 * fractional_year)
        - 0.040849 * np.sin(2 * fractional_year)
    )
    declination = (
        0.006918
        - 0.399912 * np.cos(fractional_year)
        + 0.070257 * np.sin(fractional_year)
        - 0.006758 * np.cos(2 * fractional_year)
        + 0.000907 * np.sin(2 * fractional_year)
        - 0.002697 * np.cos(3 * fractional_year)
        + 0.001480 * np.sin(3 * fractional_year)
    )

    true_solar_time = (utc_hour * 60.0 + eq_time + 4.0 * longitude) % 1440.0
    hour_angle = np.radians(true_solar_time / 4.0 - 180.0)

    lat_rad = np.radians(latitude)
    cos_zenith = np.sin(lat_rad) * np.sin(declination) + np.cos(lat_rad) * np.cos(
        declination
    ) * np.cos(hour_angle)
    cos_zenith = np.clip(cos_zenith, -1.0, 1.0)
    elevation = np.degrees(np.arcsin(cos_zenith))

    # Haurwitz clear-sky model: the ceiling irradiance for this sun angle on a
    # cloudless day. Dividing actual by this gives a clear-sky index, which is
    # essentially "how cloudy is it, really".
    clear_sky = np.where(cos_zenith > 0, 1098.0 * cos_zenith * np.exp(-0.059 / np.maximum(cos_zenith, 1e-3)), 0.0)

    return pd.DataFrame(
        {"solar_elevation_deg": elevation, "clear_sky_ghi": np.clip(clear_sky, 0.0, None)},
        index=index,
    )


# Sun this high means the site is inside its productive part of the day. Used by
# the under-generation rule so "low output" at 5am doesn't get flagged as a fault.
HIGH_GENERATION_ELEVATION_DEG = 20.0
