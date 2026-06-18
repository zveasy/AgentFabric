"""Application configuration from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import List, Union

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me-in-production"
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTFABRIC_", extra="ignore")

    app_name: str = "AgentFabric API"
    environment: str = "development"
    database_url: str = "sqlite:///./agentfabric_api.db"
    production_db_path: str = "agentfabric.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 3600
    bootstrap_token: str | None = None
    strict_signing: bool = False
    auto_migrate: bool = True
    queue_max_attempts: int = 3
    stripe_api_key: str | None = None
    stripe_webhook_secret: str | None = None
    cors_origins: List[str] = []
    rate_limit_auth_per_minute: int = 20

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v or []

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        if self.environment != "production":
            return self
        if not self.jwt_secret or self.jwt_secret == DEFAULT_JWT_SECRET or self.jwt_secret == "change-me":
            raise ValueError(
                "AGENTFABRIC_JWT_SECRET must be set to a non-default value (at least 32 chars) when "
                "AGENTFABRIC_ENVIRONMENT=production"
            )
        if len(self.jwt_secret) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(
                f"AGENTFABRIC_JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters in production"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
