"""Agent team records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class AgentTeam:
    org_id: str
    tenant_id: str
    organization_id: str
    name: str
    roles: dict[str, str] = field(default_factory=dict)
    created_by: str = ""
    team_id: str = field(default_factory=lambda: f"gov-team-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "team_id": self.team_id,
            "org_id": self.org_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "name": self.name,
            "roles": dict(self.roles),
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "AgentTeam":
        return cls(
            team_id=str(value["team_id"]),
            org_id=str(value["org_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            name=str(value["name"]),
            roles={str(k): str(v) for k, v in dict(value.get("roles", {})).items()},
            created_by=str(value.get("created_by", "")),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
            updated_at=datetime.fromisoformat(str(value["updated_at"])) if value.get("updated_at") else utc_now(),
        )
