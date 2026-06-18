"""Governance charters for agent organizations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class Charter:
    org_id: str
    tenant_id: str
    organization_id: str
    purpose: str
    authority_boundaries: tuple[str, ...] = ()
    allowed_workflow_types: tuple[str, ...] = ()
    escalation_requirements: tuple[str, ...] = ()
    budget_limits: dict[str, int] = field(default_factory=dict)
    updated_by: str = ""
    updated_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "org_id": self.org_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "purpose": self.purpose,
            "authority_boundaries": list(self.authority_boundaries),
            "allowed_workflow_types": list(self.allowed_workflow_types),
            "escalation_requirements": list(self.escalation_requirements),
            "budget_limits": dict(self.budget_limits),
            "updated_by": self.updated_by,
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "Charter":
        return cls(
            org_id=str(value["org_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            purpose=str(value.get("purpose", "")),
            authority_boundaries=tuple(str(item) for item in value.get("authority_boundaries", ())),
            allowed_workflow_types=tuple(str(item) for item in value.get("allowed_workflow_types", ())),
            escalation_requirements=tuple(str(item) for item in value.get("escalation_requirements", ())),
            budget_limits=dict(value.get("budget_limits", {})),
            updated_by=str(value.get("updated_by", "")),
            updated_at=datetime.fromisoformat(str(value["updated_at"])) if value.get("updated_at") else utc_now(),
        )
