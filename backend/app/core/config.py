"""Application configuration via pydantic-settings.

All secrets/config come from environment variables (see `.env.example`).
Nothing sensitive is ever hardcoded.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )

    # ---- Core ----
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    PROJECT_NAME: str = "Lead Generator"
    API_V1_PREFIX: str = "/api/v1"
    BACKEND_CORS_ORIGINS: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # ---- Security ----
    SECRET_KEY: str = "dev-only-insecure-change-me"
    ENCRYPTION_KEY: str = ""  # Fernet key; required in prod
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200
    JWT_ALGORITHM: str = "HS256"

    # ---- Database ----
    POSTGRES_USER: str = "leadgen"
    POSTGRES_PASSWORD: str = "leadgen_dev_password"
    POSTGRES_DB: str = "leadgen"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None

    # ---- Redis / Celery ----
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ---- AI ----
    # Provider selection: "auto" picks DeepSeek when NVIDIA_API_KEY is set, else
    # Gemma when GEMINI_API_KEY is set, else the null (never-fabricates) service.
    # Force one with "deepseek" / "gemma" / "null".
    AI_PROVIDER: str = "auto"

    # DeepSeek via an OpenAI-compatible endpoint (default: NVIDIA's inference API).
    # Used for every AI task — qualification, email/LinkedIn/follow-up generation,
    # reply classification, NL search, campaign + analytics insights, Copilot.
    NVIDIA_API_KEY: str = ""
    AI_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-ai/deepseek-v4-pro-0813"

    # Gemma via Google Generative Language API (legacy / fallback).
    GEMINI_API_KEY: str = ""
    AI_MODEL: str = "gemma-4-31b-it"

    # ---- Email (Phase 3) ----
    # Where public tracking/unsubscribe/OAuth-callback endpoints are reachable from the
    # outside world (a lead's mail client, Google/Microsoft). In dev this is the backend
    # origin; in prod a public HTTPS URL.
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    # The frontend origin OAuth flows redirect back to on success/failure.
    APP_BASE_URL: str = "http://localhost:3000"
    EMAIL_TRACKING_ENABLED: bool = True
    INBOUND_POLL_ENABLED: bool = True
    # Default "From" identity when a connected account doesn't specify one.
    DEFAULT_FROM_NAME: str = "Lead Generator"

    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    MICROSOFT_OAUTH_CLIENT_ID: str = ""
    MICROSOFT_OAUTH_CLIENT_SECRET: str = ""
    MICROSOFT_OAUTH_TENANT: str = "common"

    # Optional SMTP fallback defaults (per-account creds live encrypted in connected_accounts).
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    # ---- WhatsApp ----
    WHATSAPP_SERVICE_URL: str = "http://localhost:3100"
    WHATSAPP_SERVICE_TOKEN: str = ""

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.PUBLIC_BASE_URL}{self.API_V1_PREFIX}/accounts/oauth/google/callback"

    @property
    def microsoft_redirect_uri(self) -> str:
        return f"{self.PUBLIC_BASE_URL}{self.API_V1_PREFIX}/accounts/oauth/microsoft/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
