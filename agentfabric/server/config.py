"""Application configuration from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTFABRIC_", extra="ignore")

    app_name: str = "AgentFabric API"
    environment: str = "development"
    database_url: str = "sqlite:///./agentfabric_api.db"
    production_db_path: str = "agentfabric.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 3600
    bootstrap_token: str | None = None
    strict_signing: bool = False
    auto_migrate: bool = True
    queue_max_attempts: int = 3
    stripe_api_key: str | None = None
    stripe_webhook_secret: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
