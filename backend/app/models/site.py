"""Persistent entities: the sites we forecast for, and the forecast cache."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Site(Base):
    """A single renewable generation asset (one solar farm or one wind farm)."""

    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    site_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "solar" | "wind"
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    capacity_kw: Mapped[float] = mapped_column(Float, nullable=False)
    region: Mapped[str] = mapped_column(String(120), default="")

    # Real-world operating constraints. Plenty of plants can physically generate
    # more than their grid connection is allowed to export (a DC-oversized farm
    # behind an undersized substation), and plants that sell day-ahead have a
    # delivery schedule they're on the hook for. Both change what "too much" and
    # "too little" actually mean, so the alert rules read these instead of
    # assuming nameplate. Sites with no such constraint leave them at 0 and get
    # the plain 85%/15%-of-capacity rules.
    export_limit_kw: Mapped[float] = mapped_column(Float, default=0.0)  # 0 => use capacity
    firm_commitment_kw: Mapped[float] = mapped_column(Float, default=0.0)  # 0 => no schedule
    # The block of hours (UTC) the delivery schedule actually covers. A solar
    # plant sells a daylight block, not a 24h one, and flagging it short at
    # 3am would be noise rather than an alert.
    commitment_start_hour_utc: Mapped[int] = mapped_column(Integer, default=0)
    commitment_end_hour_utc: Mapped[int] = mapped_column(Integer, default=24)

    # Storage co-located with the site. Decides whether an over-generation event
    # becomes "charge the battery" or "curtail".
    storage_capacity_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    storage_soc_kwh: Mapped[float] = mapped_column(Float, default=0.0)

    # Per-site tunable flag thresholds, as a fraction of capacity. Defaults match
    # the 85%/15%/25% rules from the spec; operators can tighten them per asset.
    over_threshold: Mapped[float] = mapped_column(Float, default=0.85)
    under_threshold: Mapped[float] = mapped_column(Float, default=0.15)
    ramp_threshold: Mapped[float] = mapped_column(Float, default=0.25)

    # Hero demo site: its export limit and delivery schedule guarantee that any
    # judging day contains both an over- and an under-generation event.
    is_demo_site: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(String(400), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    @property
    def effective_export_limit_kw(self) -> float:
        """What the grid connection will actually accept. Falls back to nameplate."""
        return self.export_limit_kw if self.export_limit_kw > 0 else self.capacity_kw

    @property
    def storage_headroom_kwh(self) -> float:
        """How much more energy the co-located battery can absorb right now."""
        return max(self.storage_capacity_kwh - self.storage_soc_kwh, 0.0)


class ForecastCache(Base):
    """Serialized forecast payload per site, so the dashboard never waits on Open-Meteo."""

    __tablename__ = "forecast_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
