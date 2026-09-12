"""Central settings object.

We read a plain `.env` by hand rather than pulling in pydantic-settings or
python-dotenv — it's ~20 lines, keeps the install list short, and means a fresh
clone boots even with no .env file at all (every key has a sane default).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> repo root
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
ML_DIR = BACKEND_DIR / "ml"
MODEL_DIR = ML_DIR / "saved_models"
DATA_DIR = ML_DIR / "data"


def _load_dotenv() -> None:
    """Push key=value pairs from .env into os.environ without clobbering real env vars."""
    for candidate in (REPO_ROOT / ".env", BACKEND_DIR / ".env"):
        if not candidate.exists():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_dotenv()


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value if value else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: _env("GRIDPULSE_DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'gridpulse.db'}")
    )
    forecast_api: str = field(
        default_factory=lambda: _env("GRIDPULSE_FORECAST_API", "https://api.open-meteo.com/v1/forecast")
    )
    archive_api: str = field(
        default_factory=lambda: _env("GRIDPULSE_ARCHIVE_API", "https://archive-api.open-meteo.com/v1/archive")
    )
    cache_ttl_minutes: int = field(default_factory=lambda: _env_int("GRIDPULSE_CACHE_TTL_MINUTES", 20))
    refresh_interval_minutes: int = field(default_factory=lambda: _env_int("GRIDPULSE_REFRESH_INTERVAL_MINUTES", 15))
    history_months: int = field(default_factory=lambda: _env_int("GRIDPULSE_HISTORY_MONTHS", 15))
    cors_origins_raw: str = field(
        default_factory=lambda: _env("GRIDPULSE_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]

    @property
    def model_dir(self) -> Path:
        return MODEL_DIR

    @property
    def data_dir(self) -> Path:
        return DATA_DIR


settings = Settings()
