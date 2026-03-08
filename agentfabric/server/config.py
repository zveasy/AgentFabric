"""Application configuration from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTFABRIC_", extra="ignore")

    app_name: str = "AgentFabric API"
    environment: str = "development"
    database_url: str = "sqlite:///./agentfabric_api.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-production-use-at-least-32-chars"
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 3600
    stripe_api_key: Optional[str] = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
