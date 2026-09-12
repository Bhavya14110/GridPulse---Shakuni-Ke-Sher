"""The demo portfolio, and the logic that puts it in the database.

This lives in the app package rather than in the top-level `seed_data.py`
script because the API seeds itself on startup when the sites table is empty.
On a serverless host the database is ephemeral -- every cold start gets a fresh
one -- so seeding has to be something the application can do for itself, not a
command someone remembers to run.

Six real locations, three solar and three wind, spread across four continents so
the portfolio map has something to say. Coordinates are genuine — Open-Meteo
returns real weather for every one of them, so five of the six sites run on
purely live data with nothing staged.

The sixth (Bhadla Phase III) is the hero demo site described in the spec. We do
NOT fake its numbers. Instead we give it two operating constraints that are
completely ordinary in the real world and that guarantee its 72h window contains
both an over- and an under-generation event on any day of the year:

  * a substation export limit well below nameplate — extremely common for
    DC-oversized farms in India and Australia, and the single biggest cause of
    real curtailment. Midday output exceeds what the grid connection accepts,
    so the over-generation rule fires and the engine recommends curtailment.
  * a firm day-ahead delivery schedule — the plant has sold a block of power it
    must deliver. Morning and evening shoulder hours fall short of it, so the
    under-generation rule fires and the engine recommends backup/import.

Every number the UI shows for this site still comes from the live forecast and
these stored constraints; nothing is hardcoded text.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.database import Base, SessionLocal, engine, init_db
from app.models import ForecastCache, Site

SITES = [
    dict(
        name="Bhadla Phase III",
        site_type="solar",
        latitude=27.539,
        longitude=71.910,
        capacity_kw=180_000,
        region="Rajasthan, India",
        # 180 MW of panels behind a 95 MW grid connection. Everything above the
        # limit has to go somewhere: into the battery, or into the ground.
        export_limit_kw=95_000,
        # Sold 45 MW into the day-ahead market for the 03:00-12:00 UTC block
        # (08:30-17:30 local) -- the daylight hours a solar PPA covers.
        firm_commitment_kw=45_000,
        commitment_start_hour_utc=3,
        commitment_end_hour_utc=12,
        # Battery is nearly full from this morning's surplus, so it can't soak up
        # the midday peak — which is exactly when curtailment becomes the answer.
        storage_capacity_kwh=60_000,
        storage_soc_kwh=55_500,
        ramp_threshold=0.12,  # tight connection, operator holds less reserve slack
        is_demo_site=True,
        notes=(
            "DC-oversized park behind a 95 MW substation export limit, with a 45 MW "
            "day-ahead delivery schedule. Curtailment-prone by design."
        ),
    ),
    dict(
        name="Mojave Ridge Solar",
        site_type="solar",
        latitude=35.013,
        longitude=-117.871,
        capacity_kw=92_000,
        region="California, USA",
        storage_capacity_kwh=50_000,
        storage_soc_kwh=19_000,  # plenty of headroom: surplus should charge, not curtail
        notes="Utility-scale PV with a well-sized battery and an unconstrained interconnect.",
    ),
    dict(
        name="Atacama Solar One",
        site_type="solar",
        latitude=-23.501,
        longitude=-69.201,
        capacity_kw=110_000,
        region="Antofagasta, Chile",
        storage_capacity_kwh=30_000,
        storage_soc_kwh=6_500,
        notes="Highest-irradiance site in the portfolio; very low cloud variability.",
    ),
    dict(
        name="Gujarat Coastal Wind",
        site_type="wind",
        latitude=22.291,
        longitude=69.052,
        capacity_kw=120_000,
        region="Jamnagar, India",
        notes="Coastal sea-breeze regime: strong diurnal wind cycle, no storage on site.",
    ),
    dict(
        name="North Sea Alpha",
        site_type="wind",
        latitude=55.690,
        longitude=7.180,
        capacity_kw=240_000,
        region="Offshore Denmark",
        notes="Offshore array. High capacity factor, and the site most likely to hit cut-out.",
    ),
    dict(
        name="Texas Panhandle Wind",
        site_type="wind",
        latitude=35.221,
        longitude=-101.831,
        capacity_kw=150_000,
        region="Texas, USA",
        storage_capacity_kwh=80_000,
        storage_soc_kwh=27_000,
        notes="Nocturnal wind peak paired with grid-scale storage for morning shift.",
    ),
]


def seed_sites(session: Session, reset: bool = False) -> int:
    """Insert any seed site that isn't already present. Returns how many were added."""
    if reset:
        session.query(ForecastCache).delete()
        session.commit()

    existing = {name for (name,) in session.query(Site.name).all()}
    added = 0
    for spec in SITES:
        if spec["name"] in existing:
            continue
        session.add(Site(**spec))
        added += 1
    session.commit()
    return added


def rebuild_schema() -> None:
    """Drop and recreate every table.

    SQLAlchemy's create_all won't add a column to a table that already exists,
    so a schema change during development otherwise fails with a confusing
    "no such column".
    """
    Base.metadata.drop_all(bind=engine)
    init_db()


def seed_if_empty() -> int:
    """Populate an empty database. Safe to call on every startup."""
    init_db()
    session = SessionLocal()
    try:
        if session.query(Site).count():
            return 0
        return seed_sites(session)
    finally:
        session.close()
