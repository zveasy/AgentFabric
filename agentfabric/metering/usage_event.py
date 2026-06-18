"""Tenant-scoped usage event."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class UsageEvent:
    tenant_id: str
    event_type: str
    quantity: int = 1
    metadata: dict[str, object] = field(default_factory=dict)
    usage_id: str = field(default_factory=lambda: f"use-{uuid4().hex[:12]}")
    timestamp: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "usage_id": self.usage_id,
            "tenant_id": self.tenant_id,
            "event_type": self.event_type,
            "quantity": self.quantity,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "UsageEvent":
        return cls(
            usage_id=str(value["usage_id"]),
            tenant_id=str(value["tenant_id"]),
            event_type=str(value["event_type"]),
            quantity=int(value.get("quantity", 1)),
            metadata=dict(value.get("metadata", {})),
            timestamp=datetime.fromisoformat(str(value["timestamp"])),
        )
