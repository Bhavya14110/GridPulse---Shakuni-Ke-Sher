"""Cache layer in front of the forecasting pipeline.

Building a site forecast means an Open-Meteo round trip plus ~150 sequential
model calls. That's fine once; it is not fine on every page load, and a demo
that stalls for two seconds per click reads as broken. So each site's payload
is computed once, stored as JSON in SQLite, and served from there until it goes
stale. A background scheduler keeps it warm so even the first click is instant.

Everything the API serves -- forecast, alerts, recommendations, portfolio
summary -- is derived from this single cached payload, so they can never
disagree with each other.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ForecastCache, Site
from app.services import alert_engine, forecasting_service, recommendation_engine

# One site at a time: without this, six parallel page requests on a cold cache
# would each kick off their own identical rebuild.
_build_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()

DEFAULT_HORIZON_HOURS = 72


def _lock_for(site_id: int) -> threading.Lock:
    with _locks_guard:
        return _build_locks.setdefault(site_id, threading.Lock())


def _compute(site: Site) -> dict:
    payload = forecasting_service.build_site_forecast(site, DEFAULT_HORIZON_HOURS)
    alerts = alert_engine.detect_alerts(site, payload)
    payload["alerts"] = alerts
    payload["alert_summary"] = alert_engine.summarize(alerts)
    payload["recommendations"] = recommendation_engine.build_recommendations(site, alerts)
    return payload


def get_site_payload(db: Session, site: Site, force_refresh: bool = False) -> dict:
    """The site's full forecast bundle, from cache when it's still fresh."""
    now = datetime.now(timezone.utc)
    entry = (
        db.query(ForecastCache)
        .filter(ForecastCache.site_id == site.id)
        .order_by(ForecastCache.generated_at.desc())
        .first()
    )

    if entry and not force_refresh:
        # SQLite hands back naive datetimes; compare in UTC either way.
        expires = entry.expires_at.replace(tzinfo=timezone.utc)
        if expires > now:
            payload = json.loads(entry.payload_json)
            payload["cache"] = {"hit": True, "expires_at": expires.isoformat()}
            return payload

    with _lock_for(site.id):
        # Another thread may have rebuilt it while we waited for the lock.
        if not force_refresh:
            fresh = (
                db.query(ForecastCache)
                .filter(ForecastCache.site_id == site.id, ForecastCache.expires_at > now.replace(tzinfo=None))
                .first()
            )
            if fresh:
                payload = json.loads(fresh.payload_json)
                payload["cache"] = {"hit": True, "expires_at": fresh.expires_at.isoformat()}
                return payload

        payload = _compute(site)
        expires_at = now + timedelta(minutes=settings.cache_ttl_minutes)

        db.query(ForecastCache).filter(ForecastCache.site_id == site.id).delete()
        db.add(
            ForecastCache(
                site_id=site.id,
                payload_json=json.dumps(payload),
                generated_at=now.replace(tzinfo=None),
                expires_at=expires_at.replace(tzinfo=None),
            )
        )
        db.commit()

    payload["cache"] = {"hit": False, "expires_at": expires_at.isoformat()}
    return payload


def refresh_all(db: Session) -> int:
    """Rebuild every site's payload. Called by the scheduler and on startup."""
    sites = db.query(Site).order_by(Site.id).all()
    refreshed = 0
    for site in sites:
        try:
            get_site_payload(db, site, force_refresh=True)
            refreshed += 1
        except Exception as exc:
            # One unreachable site must not take the whole refresh down --
            # the rest of the portfolio is still perfectly serviceable.
            print(f"[gridpulse] refresh failed for site {site.id} ({site.name}): {exc}")
    return refreshed
