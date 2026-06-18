"""Agent organization records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class AgentOrganization:
    tenant_id: str
    organization_id: str
    name: str
    created_by: str
    org_id: str = field(default_factory=lambda: f"gov-org-{uuid4().hex[:12]}")
    authority_boundaries: tuple[str, ...] = ()
    allowed_workflow_types: tuple[str, ...] = ()
    budget_limits: dict[str, int] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "org_id": self.org_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "name": self.name,
            "authority_boundaries": list(self.authority_boundaries),
            "allowed_workflow_types": list(self.allowed_workflow_types),
            "budget_limits": dict(self.budget_limits),
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "AgentOrganization":
        return cls(
            org_id=str(value["org_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            name=str(value["name"]),
            authority_boundaries=tuple(str(item) for item in value.get("authority_boundaries", ())),
            allowed_workflow_types=tuple(str(item) for item in value.get("allowed_workflow_types", ())),
            budget_limits=dict(value.get("budget_limits", {})),
            created_by=str(value.get("created_by", "")),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
            updated_at=datetime.fromisoformat(str(value["updated_at"])) if value.get("updated_at") else utc_now(),
        )
