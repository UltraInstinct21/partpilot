"""PartPilot runtime configuration (CONTRACT v1).

Every tunable lives here so that no module reads an environment variable on its
own. Secrets are read from the environment or from a local ``.env`` file and
are NEVER returned to the browser (NFR-02).

All settings can be overridden with an environment variable that uses the
prefix ``PARTPILOT_``, e.g. ``PARTPILOT_LLM_PROVIDER=anthropic``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root: backend/shared/config.py -> backend/shared -> backend -> root
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_prefix="PARTPILOT_",
        env_file=os.getenv("PARTPILOT_ENV_FILE", str(REPO_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Paths -----------------------------------------------------------------
    data_dir: Path = Field(default=REPO_ROOT / "data")
    raw_dir: Path = Field(default=REPO_ROOT / "data" / "raw")
    pdf_dir: Path = Field(default=REPO_ROOT / "data" / "pdfs")
    cache_dir: Path = Field(default=REPO_ROOT / "data" / "cache")
    llm_cache_dir: Path = Field(default=REPO_ROOT / "data" / "llm_cache")
    contracts_dir: Path = Field(default=REPO_ROOT / "contracts")
    fixtures_dir: Path = Field(default=REPO_ROOT / "contracts" / "fixtures")
    eval_dir: Path = Field(default=REPO_ROOT / "eval")
    db_path: Path = Field(default=REPO_ROOT / "data" / "partpilot.db")

    # --- Database --------------------------------------------------------------
    database_url: str = ""
    sql_echo: bool = False

    # --- API -------------------------------------------------------------------
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_base_url: str = "http://127.0.0.1:8000"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    search_rate_limit_per_minute: int = 30
    max_upload_bytes: int = 5 * 1024 * 1024  # 5 MiB, plan WP6 "limit the size of file uploads"

    # --- LLM -------------------------------------------------------------------
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_vision_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.0
    llm_max_retries: int = 3
    llm_requests_per_second: float = 1.0
    llm_cache_enabled: bool = True
    llm_recording_enabled: bool = True
    # USD per 1M tokens. Used to estimate the cost of a call (NFR-05).
    llm_cost_per_million_input: float = 0.15
    llm_cost_per_million_output: float = 0.60

    # --- Collector credentials (server side only, NFR-02) ---------------------
    digikey_client_id: str = ""
    digikey_client_secret: str = ""
    digikey_base_url: str = "https://api.digikey.com"
    digikey_locale_site: str = "US"
    digikey_locale_language: str = "en"
    digikey_locale_currency: str = "USD"

    nexar_client_id: str = ""
    nexar_client_secret: str = ""
    nexar_token_url: str = "https://identity.nexar.com/connect/token"
    nexar_graphql_url: str = "https://api.nexar.com/graphql"
    nexar_scope: str = "supply.domain"

    mouser_api_key: str = ""
    mouser_base_url: str = "https://api.mouser.com/api/v1"

    # --- Rate limits -----------------------------------------------------------
    # DigiKey documents 120 requests/minute and 1000 requests/day. We stay below.
    digikey_rate_limit_per_minute: int = 60
    digikey_rate_limit_per_day: int = 800
    nexar_rate_limit_per_minute: int = 60
    nexar_rate_limit_per_day: int = 800
    mouser_rate_limit_per_minute: int = 20
    mouser_rate_limit_per_day: int = 800
    # Minimum delay between two requests to the same host (plan section 12).
    download_delay_seconds: float = 1.0
    request_timeout_seconds: float = 30.0
    max_retries: int = 4
    retry_backoff_seconds: float = 0.5

    # --- Ethics / scraping -----------------------------------------------------
    user_agent: str = (
        "PartPilot/0.1 (academic research; component data mining; "
        "contact: partpilot-contact@example.edu)"
    )
    respect_robots_txt: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("database_url", mode="after")
    @classmethod
    def _default_database_url(cls, v: str, info: object) -> str:
        if v:
            return v
        db_path = getattr(info, "data", {}).get("db_path") if hasattr(info, "data") else None
        if db_path is None:
            db_path = REPO_ROOT / "data" / "partpilot.db"
        return f"sqlite:///{db_path}"

    # --- Helpers ---------------------------------------------------------------

    def ensure_dirs(self) -> None:
        """Create the data directories. Safe to call repeatedly."""
        for path in (self.data_dir, self.raw_dir, self.pdf_dir, self.cache_dir, self.llm_cache_dir):
            path.mkdir(parents=True, exist_ok=True)

    def sqlite_url(self) -> str:
        """Return the SQLite URL for the configured database path."""
        return f"sqlite:///{self.db_path}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings object.

    Use this in application code; tests may call ``get_settings.cache_clear()``
    after changing the environment.
    """
    return Settings()


__all__ = ["REPO_ROOT", "Settings", "get_settings"]
