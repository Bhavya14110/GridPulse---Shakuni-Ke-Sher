"""Portfolio-level aggregation: the landing page's whole data layer in one call."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Site
from app.services import forecast_store, forecasting_service

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/summary")
def portfolio_summary(
    refresh: bool = Query(False, description="Bypass the cache and recompute every site"),
    db: Session = Depends(get_db),
):
    sites = db.query(Site).order_by(Site.id).all()

    rows = []
    total_capacity = current_output = forecast_24h_kwh = 0.0
    curtailment_at_risk_kwh = curtailment_avoidable_kwh = shortfall_kwh = 0.0
    counts = {"critical": 0, "warning": 0, "info": 0}
    sites_with_alerts = 0

    for site in sites:
        try:
            payload = forecast_store.get_site_payload(db, site, force_refresh=refresh)
        except Exception as exc:
            # A site whose weather call failed shouldn't blank the dashboard.
            rows.append(
                {
                    "id": site.id,
                    "name": site.name,
                    "site_type": site.site_type,
                    "region": site.region,
                    "latitude": site.latitude,
                    "longitude": site.longitude,
                    "capacity_kw": site.capacity_kw,
                    "is_demo_site": site.is_demo_site,
                    "status": "unavailable",
                    "error": str(exc),
                    "current_output_kw": 0.0,
                    "capacity_factor": 0.0,
                    "today_generated_kwh": 0.0,
                    "peak_forecast_kw": 0.0,
                    "alert_counts": {"critical": 0, "warning": 0, "info": 0},
                    "top_recommendation": None,
                }
            )
            continue

        summary = payload["alert_summary"]
        recommendations = payload["recommendations"]
        next_24h = payload["forecast"][:24]

        total_capacity += site.capacity_kw
        current_output += payload["current"]["output_kw"]
        forecast_24h_kwh += sum(row["predicted_kw"] for row in next_24h)

        for key in counts:
            counts[key] += summary[key]
        if summary["total"]:
            sites_with_alerts += 1

        # Headline energy numbers, summed from the same recommendations the
        # site pages show -- "avoidable" is what storage can genuinely soak up,
        # "at risk" is what still has to be spilled.
        for rec in recommendations:
            if rec["action"] == "curtail":
                curtailment_at_risk_kwh += rec["quantity_kwh"]
            elif rec["action"] == "storage_charge":
                curtailment_avoidable_kwh += rec["quantity_kwh"]
            elif rec["action"] == "backup_activation":
                shortfall_kwh += rec["quantity_kwh"]

        rows.append(
            {
                "id": site.id,
                "name": site.name,
                "site_type": site.site_type,
                "region": site.region,
                "latitude": site.latitude,
                "longitude": site.longitude,
                "capacity_kw": site.capacity_kw,
                "is_demo_site": site.is_demo_site,
                "status": summary["status"],
                "current_output_kw": payload["current"]["output_kw"],
                "capacity_factor": payload["current"]["capacity_factor"],
                "today_generated_kwh": payload["today_generated_kwh"],
                "peak_forecast_kw": round(
                    max((row["predicted_kw"] for row in next_24h), default=0.0), 1
                ),
                "alert_counts": {
                    "critical": summary["critical"],
                    "warning": summary["warning"],
                    "info": summary["info"],
                },
                "top_recommendation": recommendations[0] if recommendations else None,
            }
        )

    metrics = forecasting_service.load_metrics()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "site_count": len(sites),
        "total_capacity_kw": round(total_capacity, 1),
        "current_output_kw": round(current_output, 1),
        "portfolio_capacity_factor": round(current_output / total_capacity, 4)
        if total_capacity
        else 0.0,
        "forecast_24h_mwh": round(forecast_24h_kwh / 1000, 1),
        "sites_with_alerts": sites_with_alerts,
        "alert_counts": counts,
        "curtailment_at_risk_mwh": round(curtailment_at_risk_kwh / 1000, 1),
        "curtailment_avoidable_mwh": round(curtailment_avoidable_kwh / 1000, 1),
        "shortfall_to_cover_mwh": round(shortfall_kwh / 1000, 1),
        "sites": rows,
        "model": {
            "trained_at": metrics.get("trained_at"),
            "dataset_rows": metrics.get("dataset_rows"),
            "dataset_span": metrics.get("dataset_span"),
            "solar": metrics.get("models", {}).get("solar", {}),
            "wind": metrics.get("models", {}).get("wind", {}),
        },
    }
