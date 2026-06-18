"""Cloud runtime workers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class Worker:
    tenant_id: str
    worker_id: str = field(default_factory=lambda: f"worker-{uuid4().hex[:12]}")
    queue_names: tuple[str, ...] = ("default",)
    capabilities: tuple[str, ...] = ()
    status: str = "registered"
    lease_until: datetime | None = None
    registered_at: datetime = field(default_factory=utc_now)
    last_heartbeat_at: datetime = field(default_factory=utc_now)

    def heartbeat(self, lease_seconds: int = 60) -> "Worker":
        now = utc_now()
        return Worker(
            worker_id=self.worker_id,
            tenant_id=self.tenant_id,
            queue_names=self.queue_names,
            capabilities=self.capabilities,
            status="healthy",
            lease_until=now + timedelta(seconds=lease_seconds),
            registered_at=self.registered_at,
            last_heartbeat_at=now,
        )

    def is_stale(self, timeout_seconds: int) -> bool:
        return utc_now() - self.last_heartbeat_at > timedelta(seconds=timeout_seconds)

    def as_dict(self) -> dict[str, object]:
        return {
            "worker_id": self.worker_id,
            "tenant_id": self.tenant_id,
            "queue_names": list(self.queue_names),
            "capabilities": list(self.capabilities),
            "status": self.status,
            "lease_until": self.lease_until.isoformat() if self.lease_until else None,
            "registered_at": self.registered_at.isoformat(),
            "last_heartbeat_at": self.last_heartbeat_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "Worker":
        return cls(
            worker_id=str(value["worker_id"]),
            tenant_id=str(value["tenant_id"]),
            queue_names=tuple(str(item) for item in value.get("queue_names", ("default",))),
            capabilities=tuple(str(item) for item in value.get("capabilities", ())),
            status=str(value.get("status", "registered")),
            lease_until=datetime.fromisoformat(str(value["lease_until"])) if value.get("lease_until") else None,
            registered_at=datetime.fromisoformat(str(value["registered_at"])) if value.get("registered_at") else utc_now(),
            last_heartbeat_at=datetime.fromisoformat(str(value["last_heartbeat_at"])) if value.get("last_heartbeat_at") else utc_now(),
        )
