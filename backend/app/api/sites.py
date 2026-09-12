"""Site CRUD, weather, forecast, alerts, recommendations, historical accuracy."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import ForecastCache, Site
from app.schemas import SiteCreate, SiteOut
from app.services import forecast_store, forecasting_service

router = APIRouter(prefix="/api/sites", tags=["sites"])


def _get_site(db: Session, site_id: int) -> Site:
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail=f"No site with id {site_id}")
    return site


@router.get("", response_model=list[SiteOut])
def list_sites(db: Session = Depends(get_db)):
    return db.query(Site).order_by(Site.id).all()


@router.post("", response_model=SiteOut, status_code=201)
def create_site(payload: SiteCreate, db: Session = Depends(get_db)):
    """Add a site. It starts forecasting immediately -- no retraining needed.

    That falls out of predicting capacity factor rather than kW: the solar model
    already knows how panels behave, so a brand new 30 MW site anywhere on earth
    just needs its coordinates fed to Open-Meteo.
    """
    site = Site(**payload.model_dump())
    db.add(site)
    db.commit()
    db.refresh(site)
    return site


@router.delete("/{site_id}", status_code=204)
def delete_site(site_id: int, db: Session = Depends(get_db)):
    site = _get_site(db, site_id)
    db.query(ForecastCache).filter(ForecastCache.site_id == site_id).delete()
    db.delete(site)
    db.commit()


@router.get("/{site_id}")
def get_site(site_id: int, db: Session = Depends(get_db)):
    site = _get_site(db, site_id)
    return SiteOut.model_validate(site).model_dump()


@router.get("/{site_id}/weather")
def get_weather(site_id: int, db: Session = Depends(get_db)):
    """Current conditions plus the hourly forecast weather driving the prediction."""
    site = _get_site(db, site_id)
    payload = forecast_store.get_site_payload(db, site)
    return {
        "site_id": site.id,
        "site_name": site.name,
        "current": payload["current"]["weather"],
        "hourly": [
            {"timestamp": row["timestamp"], **row["weather"]} for row in payload["forecast"]
        ],
    }


@router.get("/{site_id}/forecast")
def get_forecast(
    site_id: int,
    hours: int = Query(72, ge=1, le=72),
    refresh: bool = Query(False, description="Bypass the cache and recompute"),
    db: Session = Depends(get_db),
):
    """Hourly predicted generation with an 80% confidence band."""
    site = _get_site(db, site_id)
    payload = forecast_store.get_site_payload(db, site, force_refresh=refresh)

    trimmed = dict(payload)
    trimmed["forecast"] = payload["forecast"][:hours]
    trimmed["horizon_hours"] = len(trimmed["forecast"])
    # Alerts and recommendations are computed over the full 72h window, so drop
    # any that start beyond the horizon the caller actually asked for.
    if hours < len(payload["forecast"]):
        cutoff = trimmed["forecast"][-1]["timestamp"]
        trimmed["alerts"] = [a for a in payload["alerts"] if a["start"] <= cutoff]
        trimmed["recommendations"] = [
            r for r in payload["recommendations"] if r["window_start"] <= cutoff
        ]
    return trimmed


@router.get("/{site_id}/historical")
def get_historical(
    site_id: int,
    days: int = Query(7, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """Rolling day-ahead backtest: what we would have forecast vs. what happened.

    Not cached alongside the main payload because it's a different (and heavier)
    computation, and the dashboard only asks for it on the site detail page.
    """
    site = _get_site(db, site_id)
    return forecasting_service.rolling_backtest(site, days)


@router.get("/{site_id}/alerts")
def get_alerts(site_id: int, db: Session = Depends(get_db)):
    site = _get_site(db, site_id)
    payload = forecast_store.get_site_payload(db, site)
    return {
        "site_id": site.id,
        "site_name": site.name,
        "generated_at": payload["generated_at"],
        "summary": payload["alert_summary"],
        "alerts": payload["alerts"],
        "thresholds": {
            "over_threshold": site.over_threshold,
            "under_threshold": site.under_threshold,
            "ramp_threshold": site.ramp_threshold,
            "export_limit_kw": site.effective_export_limit_kw,
            "firm_commitment_kw": site.firm_commitment_kw,
            "capacity_kw": site.capacity_kw,
        },
    }


@router.get("/{site_id}/recommendations")
def get_recommendations(site_id: int, db: Session = Depends(get_db)):
    site = _get_site(db, site_id)
    payload = forecast_store.get_site_payload(db, site)
    return {
        "site_id": site.id,
        "site_name": site.name,
        "generated_at": payload["generated_at"],
        "recommendations": payload["recommendations"],
    }
