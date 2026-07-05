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
    veil_api_url: str | None = None
    federation_enabled: bool = True
    auto_migrate: bool = True
    queue_max_attempts: int = 3
    cloud_queue_backend: str = "memory"
    cloud_queue_sqlite_path: str = "agentfabric_runtime_queue.db"
    worker_lease_seconds: int = 60
    worker_heartbeat_timeout_seconds: int = 90
    stripe_api_key: str | None = None
    stripe_webhook_secret: str | None = None
    cors_origins: List[str] = []
    rate_limit_auth_per_minute: int = 20
    metrics_public: bool = False
    log_level: str = "INFO"
    json_logs: bool = True  # set False for dev console; production uses True
    factory_output_root: str = "/tmp/agentfabric-generated"
    state_store_backend: str = "sqlite"
    state_store_path: str | None = None
    renovation_storage_dir: str = "/tmp/agentfabric-renovation-storage"
    renovation_max_upload_bytes: int = 10_000_000
    renovation_email_provider: str = "local"
    renovation_smtp_host: str | None = None
    renovation_smtp_port: int = 587
    renovation_smtp_username: str | None = None
    renovation_smtp_password: str | None = None
    renovation_email_sender: str = "renovationos@example.local"
    renovation_email_reply_to: str | None = None
    renovation_smtp_live_enabled: bool = False
    renovation_sms_provider: str = "local"
    renovation_sms_sender_id: str | None = None
    renovation_sms_account_sid: str | None = None
    renovation_sms_auth_token: str | None = None
    renovation_calendar_provider: str = "local"
    renovation_calendar_oauth_client_id: str | None = None
    renovation_calendar_oauth_client_secret: str | None = None
    renovation_payment_provider: str = "local"
    renovation_payment_secret_key: str | None = None
    renovation_payment_webhook_secret: str | None = None

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
