"""Seed the demo portfolio.

Run this once after install:

    python seed_data.py            # add any missing sites
    python seed_data.py --reset    # rebuild the schema from scratch first

The portfolio itself is defined in `app/core/seed.py`, because the API seeds
itself on startup when the database is empty -- which is what makes a
serverless deployment, where the database does not survive between cold starts,
work at all.
"""
from __future__ import annotations

import sys

from app.core.seed import rebuild_schema, seed_if_empty, seed_sites
from app.core.database import SessionLocal, init_db
from app.models import Site


def main(reset: bool = False) -> None:
    if reset:
        rebuild_schema()
    else:
        init_db()

    session = SessionLocal()
    try:
        added = seed_sites(session, reset=reset)
        total = session.query(Site).count()
        print(f"Seeded {added} new site(s). Portfolio now holds {total} sites:")
        for site in session.query(Site).order_by(Site.id).all():
            flag = "  <- hero demo site" if site.is_demo_site else ""
            print(
                f"  [{site.id}] {site.name:<24} {site.site_type:<5} "
                f"{site.capacity_kw/1000:>6.0f} MW  {site.region}{flag}"
            )
    finally:
        session.close()


if __name__ == "__main__":
    main(reset="--reset" in sys.argv)
