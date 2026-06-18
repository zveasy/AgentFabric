"""Tenant-scoped revenue events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class RevenueEvent:
    tenant_id: str
    category: str
    amount: float
    source_id: str = ""
    package_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    currency: str = "USD"
    event_id: str = field(default_factory=lambda: f"rev-{uuid4().hex[:12]}")
    timestamp: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "category": self.category,
            "amount": self.amount,
            "currency": self.currency,
            "source_id": self.source_id,
            "package_id": self.package_id,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "RevenueEvent":
        return cls(
            event_id=str(value["event_id"]),
            tenant_id=str(value["tenant_id"]),
            category=str(value["category"]),
            amount=float(value["amount"]),
            currency=str(value.get("currency", "USD")),
            source_id=str(value.get("source_id", "")),
            package_id=str(value["package_id"]) if value.get("package_id") else None,
            metadata=dict(value.get("metadata", {})),
            timestamp=datetime.fromisoformat(str(value["timestamp"])) if value.get("timestamp") else utc_now(),
        )
