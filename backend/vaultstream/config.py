"""Application configuration, loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_ROOT


class Settings(BaseSettings):
    """Runtime settings.

    Values come from environment variables, falling back to ``backend/.env``.
    See ``.env.example`` for the full documented list.
    """

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core ---
    environment: str = "development"
    debug: bool = True

    # --- Database ---
    database_url: str = (
        "postgresql+psycopg://vaultstream:vaultstream@localhost:5433/vaultstream"
    )

    # --- CORS ---
    # Explicit origins are required: `allow_credentials=True` is incompatible
    # with a wildcard origin, and we ship JWTs in cookies.
    # NoDecode stops pydantic-settings from JSON-decoding the raw env value so
    # the validator below can accept a plain comma-separated string.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )

    # --- Auth ---
    # MUST be overridden in any non-development environment.
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    cookie_secure: bool = False  # True behind HTTPS in production
    cookie_domain: str | None = None

    # --- TMDB (only needed for trailer/backdrop resolution, Task 8) ---
    tmdb_api_key: str | None = None
    tmdb_api_base: str = "https://api.themoviedb.org/3"
    tmdb_image_base: str = "https://image.tmdb.org/t/p"

    # --- Catalog behaviour ---
    # Browse surfaces hide near-empty records; this is the vote_count floor.
    quality_floor_vote_count: int = 10
    default_page_size: int = 24
    max_page_size: int = 100

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Allow CORS_ORIGINS to be given as a comma-separated string."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return value  # let pydantic parse JSON
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (import-safe, cheap to call repeatedly)."""
    return Settings()
