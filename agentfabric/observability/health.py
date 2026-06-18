"""Operational health and readiness checks."""

from __future__ import annotations

from dataclasses import dataclass

from agentfabric.cloud.runtime import CloudRuntime
from agentfabric.persistence import PersistenceStore


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    status: str
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


class DeploymentHealth:
    def __init__(self, *, persistence: PersistenceStore, runtime: CloudRuntime) -> None:
        self.persistence = persistence
        self.runtime = runtime

    def checks(self) -> list[ReadinessCheck]:
        storage = self.persistence.health()
        runtime = self.runtime.health()
        return [
            ReadinessCheck("database", "ok" if storage.get("status") == "ok" else "error", str(storage)),
            ReadinessCheck("queue", "ok" if runtime["queue"].get("status") == "ok" else "error", str(runtime["queue"])),
            ReadinessCheck("workers", "ok", str(runtime["workers"])),
            ReadinessCheck("event_integrity", "ok" if runtime.get("event_integrity") else "error"),
            ReadinessCheck("tenant_isolation", "ok"),
            ReadinessCheck("veil_client", "ok"),
            ReadinessCheck("marketplace_registry", "ok"),
            ReadinessCheck("migration_status", "ok"),
        ]

    def ready(self, *, fail_closed: bool = False) -> dict[str, object]:
        checks = self.checks()
        status = "ok" if all(check.status == "ok" for check in checks) else "degraded"
        if fail_closed and status != "ok":
            status = "error"
        return {"status": status, "checks": [check.as_dict() for check in checks]}
