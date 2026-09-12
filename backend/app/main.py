"""GridPulse API entrypoint.

Run it with:
    uvicorn app.main:app --reload --port 8000

Interactive docs land at http://localhost:8000/docs.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import portfolio, sites
from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.services import forecast_store, forecasting_service

_scheduler: BackgroundScheduler | None = None


def _refresh_job() -> None:
    """Keep every site's cached forecast warm so the dashboard never waits."""
    db = SessionLocal()
    try:
        count = forecast_store.refresh_all(db)
        print(f"[gridpulse] background refresh complete: {count} site(s)")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    init_db()

    if settings.refresh_interval_minutes > 0:
        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.add_job(
            _refresh_job,
            "interval",
            minutes=settings.refresh_interval_minutes,
            id="forecast_refresh",
            max_instances=1,
            coalesce=True,
            # Fire once almost immediately so the cache is warm before anyone
            # opens the dashboard. Building all six sites means six Open-Meteo
            # round trips; doing that while the browser waits is the difference
            # between a demo that feels instant and one that looks broken.
            next_run_time=datetime.now() + timedelta(seconds=2),
        )
        _scheduler.start()
        print(
            f"[gridpulse] scheduler running, warming cache now and refreshing every "
            f"{settings.refresh_interval_minutes} min"
        )

    yield

    if _scheduler is not None:
        _scheduler.shutdown(wait=False)


app = FastAPI(
    title="GridPulse API",
    version="1.0.0",
    summary="Renewable generation forecasting, risk flagging and grid-action recommendations.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sites.router)
app.include_router(portfolio.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    """Cheap readiness probe that also says whether the models are trained."""
    metrics = forecasting_service.load_metrics()
    return {
        "status": "ok",
        "models_trained": bool(metrics),
        "trained_at": metrics.get("trained_at"),
        "cache_ttl_minutes": settings.cache_ttl_minutes,
        "refresh_interval_minutes": settings.refresh_interval_minutes,
    }


@app.get("/api/model/metrics", tags=["meta"])
def model_metrics() -> dict:
    """Full training report, as written by ml/train_model.py.

    The dashboard's accuracy panel reads this directly, so the numbers on screen
    are literally the numbers the training run produced -- there's nowhere for
    them to drift apart.
    """
    metrics = forecasting_service.load_metrics()
    if not metrics:
        return {
            "trained": False,
            "message": (
                "No trained models found. Run `python ml/build_historical_dataset.py` "
                "then `python ml/train_model.py`."
            ),
        }
    return {"trained": True, **metrics}


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "name": "GridPulse",
        "docs": "/docs",
        "endpoints": [
            "/api/sites",
            "/api/sites/{id}/weather",
            "/api/sites/{id}/forecast?hours=72",
            "/api/sites/{id}/historical?days=7",
            "/api/sites/{id}/alerts",
            "/api/sites/{id}/recommendations",
            "/api/portfolio/summary",
            "/api/model/metrics",
        ],
    }
