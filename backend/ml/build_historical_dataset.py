"""Build the historical generation record we train on.

There is no way to get real utility SCADA output in a hackathon window, so we
manufacture a *weather-correlated* history instead of inventing numbers: pull
15 months of real ERA5 reanalysis weather for each seeded site from Open-Meteo's
archive, then replay it through the physics model in
`app/services/generation_model.py`.

What comes out is a plausible hourly generation record for each real site that
carries all the structure that matters — the diurnal cycle, the seasonal swing,
cloud events, storm shutdowns, the temperature derate in summer. That structure
is what the ML model actually learns. Swap this file for a CSV of real SCADA
data and nothing downstream has to change.

Usage:
    python ml/build_historical_dataset.py            # all seeded sites
    python ml/build_historical_dataset.py --months 6 # shorter pull, faster
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import DATA_DIR, settings  # noqa: E402
from app.core.database import SessionLocal, init_db  # noqa: E402
from app.models import Site  # noqa: E402
from app.services import weather_service  # noqa: E402
from app.services.generation_model import generation_from_weather  # noqa: E402

OUTPUT_PATH = DATA_DIR / "historical_generation.csv"


def build_for_site(site: Site, months: int) -> pd.DataFrame:
    start, end = weather_service.archive_window(months)
    print(f"  fetching {start} -> {end} for {site.name} ...", end="", flush=True)
    began = time.time()
    weather = weather_service.fetch_archive(site.latitude, site.longitude, start, end)
    print(f" {len(weather)} hours in {time.time() - began:.1f}s")

    # Seed the noise per site so a rebuild is reproducible.
    generation = generation_from_weather(
        site.site_type, site.capacity_kw, weather, add_noise=True, seed=site.id * 101
    )

    frame = weather.copy()
    frame["generation_kw"] = generation
    frame["capacity_factor"] = (generation / site.capacity_kw).clip(0.0, 1.0)
    frame["site_id"] = site.id
    frame["site_name"] = site.name
    frame["site_type"] = site.site_type
    frame["capacity_kw"] = site.capacity_kw
    frame["latitude"] = site.latitude
    frame["longitude"] = site.longitude
    return frame.reset_index().rename(columns={"time": "timestamp"})


def sanity_report(frame: pd.DataFrame) -> None:
    """Print enough to eyeball that the physics didn't go sideways."""
    print("\nSanity check (mean capacity factor by UTC hour):")
    for site_type in sorted(frame["site_type"].unique()):
        subset = frame[frame["site_type"] == site_type]
        for name, group in subset.groupby("site_name"):
            hourly = group.groupby(group["timestamp"].dt.hour)["capacity_factor"].mean()
            peak_hour = int(hourly.idxmax())
            night = group[group["shortwave_radiation"] == 0]["generation_kw"]
            print(
                f"  {name:<24} {site_type:<5} "
                f"mean CF {group['capacity_factor'].mean():.3f}  "
                f"peak CF {group['capacity_factor'].max():.3f}  "
                f"peak hour {peak_hour:02d}:00 UTC  "
                f"dark-hour output {night.max() if len(night) else 0:.0f} kW"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--months", type=int, default=settings.history_months)
    args = parser.parse_args()

    init_db()
    session = SessionLocal()
    try:
        sites = session.query(Site).order_by(Site.id).all()
    finally:
        session.close()

    if not sites:
        raise SystemExit("No sites in the database. Run `python seed_data.py` first.")

    print(f"Building {args.months} months of history for {len(sites)} site(s)")
    frames = [build_for_site(site, args.months) for site in sites]
    combined = pd.concat(frames, ignore_index=True)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUTPUT_PATH, index=False)

    sanity_report(combined)
    span = f"{combined['timestamp'].min():%Y-%m-%d} to {combined['timestamp'].max():%Y-%m-%d}"
    print(f"\nWrote {len(combined):,} rows ({span}) -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
