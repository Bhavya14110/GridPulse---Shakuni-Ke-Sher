"""Pydantic schemas for request/response bodies.

Responses that are just pass-throughs of the cached forecast payload are
returned as plain dicts -- wrapping a deeply nested, already-validated payload
in models would cost a serialization pass per request and buy nothing. The
schemas here cover what actually needs validating: input, and the shapes the
frontend types itself against.
"""
from app.schemas.site import (
    AlertOut,
    PortfolioSiteOut,
    PortfolioSummaryOut,
    RecommendationOut,
    SiteCreate,
    SiteOut,
)

__all__ = [
    "SiteCreate",
    "SiteOut",
    "PortfolioSiteOut",
    "PortfolioSummaryOut",
    "AlertOut",
    "RecommendationOut",
]
