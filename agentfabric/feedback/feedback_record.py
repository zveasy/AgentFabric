"""Tenant-scoped feedback records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class FeedbackRecord:
    tenant_id: str
    organization_id: str
    target_type: str
    target_id: str
    feedback_type: str
    created_by: str
    rating: float | None = None
    notes: str = ""
    correction_id: str | None = None
    feedback_id: str = field(default_factory=lambda: f"feedback-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "feedback_id": self.feedback_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "feedback_type": self.feedback_type,
            "rating": self.rating,
            "notes": self.notes,
            "correction_id": self.correction_id,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "FeedbackRecord":
        return cls(
            feedback_id=str(value["feedback_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            target_type=str(value["target_type"]),
            target_id=str(value["target_id"]),
            feedback_type=str(value["feedback_type"]),
            rating=float(value["rating"]) if value.get("rating") is not None else None,
            notes=str(value.get("notes", "")),
            correction_id=str(value["correction_id"]) if value.get("correction_id") else None,
            created_by=str(value.get("created_by", "")),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
        )
