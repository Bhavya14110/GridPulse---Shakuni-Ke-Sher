from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SiteCreate(BaseModel):
    """Payload for adding a site from the dashboard.

    Only the five fields an operator actually knows off the top of their head
    are required; everything else falls back to the standard thresholds.
    """

    name: str = Field(min_length=1, max_length=120)
    site_type: Literal["solar", "wind"]
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    capacity_kw: float = Field(gt=0, le=5_000_000)

    region: str = Field(default="", max_length=120)
    export_limit_kw: float = Field(default=0.0, ge=0)
    firm_commitment_kw: float = Field(default=0.0, ge=0)
    commitment_start_hour_utc: int = Field(default=0, ge=0, le=23)
    commitment_end_hour_utc: int = Field(default=24, ge=1, le=24)
    storage_capacity_kwh: float = Field(default=0.0, ge=0)
    storage_soc_kwh: float = Field(default=0.0, ge=0)
    over_threshold: float = Field(default=0.85, gt=0, le=1.0)
    under_threshold: float = Field(default=0.15, ge=0, lt=1.0)
    ramp_threshold: float = Field(default=0.25, gt=0, le=1.0)
    notes: str = Field(default="", max_length=400)

    @field_validator("under_threshold")
    @classmethod
    def _under_below_over(cls, value: float, info):
        over = info.data.get("over_threshold", 0.85)
        if value >= over:
            raise ValueError("under_threshold must sit below over_threshold")
        return value

    @field_validator("commitment_end_hour_utc")
    @classmethod
    def _window_ordered(cls, value: int, info):
        start = info.data.get("commitment_start_hour_utc", 0)
        if value <= start:
            raise ValueError("commitment_end_hour_utc must be after commitment_start_hour_utc")
        return value


class SiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    site_type: str
    latitude: float
    longitude: float
    capacity_kw: float
    region: str
    export_limit_kw: float
    firm_commitment_kw: float
    commitment_start_hour_utc: int
    commitment_end_hour_utc: int
    storage_capacity_kwh: float
    storage_soc_kwh: float
    over_threshold: float
    under_threshold: float
    ramp_threshold: float
    is_demo_site: bool
    notes: str


class AlertOut(BaseModel):
    id: str
    type: str
    severity: str
    start: str
    end: str
    duration_hours: int
    headline: str
    detail: str


class RecommendationOut(BaseModel):
    id: str
    site_id: int
    alert_id: str
    action: str
    title: str
    severity: str
    window_start: str
    window_end: str
    quantity_kwh: float
    reason: str


class PortfolioSiteOut(BaseModel):
    """One row of the portfolio view: enough to draw a map pin and a card."""

    id: int
    name: str
    site_type: str
    region: str
    latitude: float
    longitude: float
    capacity_kw: float
    is_demo_site: bool
    status: str
    current_output_kw: float
    capacity_factor: float
    today_generated_kwh: float
    peak_forecast_kw: float
    alert_counts: dict
    top_recommendation: RecommendationOut | None = None


class PortfolioSummaryOut(BaseModel):
    generated_at: str
    site_count: int
    total_capacity_kw: float
    current_output_kw: float
    portfolio_capacity_factor: float
    forecast_24h_mwh: float
    sites_with_alerts: int
    alert_counts: dict
    curtailment_at_risk_mwh: float
    curtailment_avoidable_mwh: float
    shortfall_to_cover_mwh: float
    sites: list[PortfolioSiteOut]
    model: dict
