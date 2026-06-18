"""Federated delivery receipts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class FederatedReceipt:
    message_id: str
    tenant_id: str
    status: str
    reason: str = ""
    receipt_id: str = field(default_factory=lambda: f"fed-receipt-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "receipt_id": self.receipt_id,
            "message_id": self.message_id,
            "tenant_id": self.tenant_id,
            "status": self.status,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "FederatedReceipt":
        return cls(
            receipt_id=str(value["receipt_id"]),
            message_id=str(value["message_id"]),
            tenant_id=str(value["tenant_id"]),
            status=str(value["status"]),
            reason=str(value.get("reason", "")),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
        )
