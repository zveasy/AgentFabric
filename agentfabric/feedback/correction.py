"""Correction records for feedback loops."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class Correction:
    tenant_id: str
    target_type: str
    target_id: str
    notes: str
    correction_id: str = field(default_factory=lambda: f"correction-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "correction_id": self.correction_id,
            "tenant_id": self.tenant_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "Correction":
        return cls(
            correction_id=str(value["correction_id"]),
            tenant_id=str(value["tenant_id"]),
            target_type=str(value["target_type"]),
            target_id=str(value["target_id"]),
            notes=str(value.get("notes", "")),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
        )
