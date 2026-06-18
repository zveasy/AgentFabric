"""Production safety validation for AgentFabric settings."""

from __future__ import annotations

from dataclasses import dataclass

from agentfabric.server.config import DEFAULT_JWT_SECRET, MIN_JWT_SECRET_LENGTH, Settings


@dataclass(frozen=True)
class SafetyCheck:
    name: str
    ok: bool
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


class ProductionSafetyError(RuntimeError):
    """Raised when production configuration is unsafe."""


def validate_production_safety(settings: Settings) -> list[SafetyCheck]:
    checks = [
        SafetyCheck("environment", settings.environment == "production", settings.environment),
        SafetyCheck(
            "jwt_secret",
            bool(settings.jwt_secret)
            and settings.jwt_secret not in {DEFAULT_JWT_SECRET, "change-me"}
            and len(settings.jwt_secret) >= MIN_JWT_SECRET_LENGTH,
            "non-default secret with minimum length",
        ),
        SafetyCheck("database_url", not settings.database_url.startswith("sqlite:"), settings.database_url),
        SafetyCheck("queue_backend", settings.cloud_queue_backend in {"redis", "sqlite"}, settings.cloud_queue_backend),
        SafetyCheck("redis_url", settings.cloud_queue_backend != "redis" or settings.redis_url.startswith("redis://"), settings.redis_url),
        SafetyCheck("veil_api_url", bool(settings.veil_api_url), settings.veil_api_url or "missing"),
        SafetyCheck("package_signing", settings.strict_signing, "strict signing required"),
        SafetyCheck("federation", not settings.federation_enabled or settings.strict_signing, "federation requires strict signing"),
    ]
    failed = [check for check in checks if not check.ok]
    if settings.environment == "production" and failed:
        details = ", ".join(f"{check.name}: {check.detail}" for check in failed)
        raise ProductionSafetyError(f"unsafe production configuration: {details}")
    return checks
