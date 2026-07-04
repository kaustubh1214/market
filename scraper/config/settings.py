"""Runtime settings loaded from environment variables / .env file.

All knobs documented in `.env.example`. Access settings through
:func:`get_settings` so the `.env` file is loaded exactly once.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of all runtime configuration."""

    # Database
    database_url: str = "sqlite:///data/scraper.db"

    # HTTP behaviour
    request_delay_seconds: float = 1.5
    request_jitter_seconds: float = 1.0
    request_timeout_seconds: int = 40
    max_retries: int = 4
    retry_backoff_base: float = 2.0

    # Static-data cache policy
    static_refresh_days: int = 30

    # Index / sector selection
    indices: list[str] = field(default_factory=list)  # empty -> registry default
    it_industry_values: list[str] = field(
        default_factory=lambda: ["Information Technology"]
    )
    it_mc_sector_values: list[str] = field(
        default_factory=lambda: ["Software & IT Services", "IT Services & Consulting"]
    )

    # Export
    export_dir: Path = PROJECT_ROOT / "exports"
    export_excel: bool = True
    export_csv: bool = False

    # Logging / state
    log_dir: Path = PROJECT_ROOT / "logs"
    log_level: str = "INFO"
    data_dir: Path = PROJECT_ROOT / "data"

    @property
    def checkpoint_path(self) -> Path:
        return self.data_dir / "checkpoint.json"

    def is_it_industry(self, nse_industry: str | None) -> bool:
        """True when the NSE-reported industry counts as IT."""
        if not nse_industry:
            return False
        wanted = {v.lower() for v in self.it_industry_values}
        return nse_industry.strip().lower() in wanted

    def is_it_mc_sector(self, mc_sector: str | None) -> bool:
        """True when the Moneycontrol-reported sector counts as IT."""
        if not mc_sector:
            return False
        wanted = {v.lower() for v in self.it_mc_sector_values}
        return mc_sector.strip().lower() in wanted


def load_settings() -> Settings:
    """Build a :class:`Settings` from environment variables (.env aware)."""
    load_dotenv(PROJECT_ROOT / ".env")

    export_dir = Path(_env_str("EXPORT_DIR", "exports"))
    if not export_dir.is_absolute():
        export_dir = PROJECT_ROOT / export_dir
    log_dir = Path(_env_str("LOG_DIR", "logs"))
    if not log_dir.is_absolute():
        log_dir = PROJECT_ROOT / log_dir

    return Settings(
        database_url=_env_str("DATABASE_URL", "sqlite:///data/scraper.db"),
        request_delay_seconds=_env_float("REQUEST_DELAY_SECONDS", 1.5),
        request_jitter_seconds=_env_float("REQUEST_JITTER_SECONDS", 1.0),
        request_timeout_seconds=_env_int("REQUEST_TIMEOUT_SECONDS", 40),
        max_retries=_env_int("MAX_RETRIES", 4),
        retry_backoff_base=_env_float("RETRY_BACKOFF_BASE", 2.0),
        static_refresh_days=_env_int("STATIC_REFRESH_DAYS", 30),
        indices=_env_list("INDICES", []),
        it_industry_values=_env_list(
            "IT_INDUSTRY_VALUES", ["Information Technology"]
        ),
        it_mc_sector_values=_env_list(
            "IT_MC_SECTOR_VALUES",
            ["Software & IT Services", "IT Services & Consulting"],
        ),
        export_dir=export_dir,
        export_excel=_env_bool("EXPORT_EXCEL", True),
        export_csv=_env_bool("EXPORT_CSV", False),
        log_dir=log_dir,
        log_level=_env_str("LOG_LEVEL", "INFO").upper(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return load_settings()
