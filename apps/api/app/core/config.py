"""Application settings. Everything environment-specific lives here."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """A required integration is not configured. Surfaced as HTTP 503 with setup guidance."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    environment: str = "development"
    database_url: str = ""
    database_pool_size: int = 5

    clerk_issuer: str = ""
    clerk_jwks_url: str = ""
    clerk_secret_key: str = ""
    clerk_authorized_parties: str = ""
    bootstrap_admin_emails: str = ""

    storage_provider: str = "supabase"  # supabase | local
    local_storage_dir: str = "./.storage"
    public_api_url: str = "http://localhost:8000"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "evalai-private"

    gemini_api_key: str = ""
    gemini_model: str = ""
    gemini_vision_model: str = ""
    gemini_embedding_model: str = ""
    gemini_base_url: str = ""
    embedding_dimensions: int = 768
    ai_request_timeout: int = 120
    ai_max_retries: int = 3

    app_signing_secret: str = ""
    cors_origins: str = "http://localhost:3000"
    max_upload_size_mb: int = 50
    max_answer_sheet_pages: int = 80
    signed_url_ttl_seconds: int = 300
    ai_rate_limit_per_minute: int = 10
    ocr_review_threshold: float = Field(0.75, ge=0, le=1)
    evaluation_review_threshold: float = Field(0.7, ge=0, le=1)

    worker_poll_seconds: float = 2.0
    worker_lock_timeout_seconds: int = 900

    @field_validator("database_url")
    @classmethod
    def _driver(cls, v: str) -> str:
        for prefix in ("postgresql://", "postgres://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def bootstrap_admins(self) -> set[str]:
        return {e.strip().lower() for e in self.bootstrap_admin_emails.split(",") if e.strip()}

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def signing_secret(self) -> str:
        if not self.app_signing_secret:
            raise ConfigurationError("APP_SIGNING_SECRET is not set. Generate one with `openssl rand -hex 32`.")
        return self.app_signing_secret


@lru_cache
def get_settings() -> Settings:
    return Settings()
