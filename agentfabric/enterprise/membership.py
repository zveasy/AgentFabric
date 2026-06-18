"""Enterprise membership model and service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from agentfabric.persistence import PersistenceStore


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class Membership:
    principal_id: str
    tenant_id: str
    organization_id: str
    role: str
    member_type: str
    created_by: str
    team_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def membership_id(self) -> str:
        return f"{self.tenant_id}:{self.principal_id}"

    def as_dict(self) -> dict[str, object]:
        return {
            "membership_id": self.membership_id,
            "principal_id": self.principal_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "role": self.role,
            "member_type": self.member_type,
            "team_id": self.team_id,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "Membership":
        return cls(
            principal_id=str(value["principal_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            role=str(value["role"]),
            member_type=str(value.get("member_type", "user")),
            team_id=str(value["team_id"]) if value.get("team_id") else None,
            created_by=str(value["created_by"]),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            updated_at=datetime.fromisoformat(str(value["updated_at"])),
        )


class MembershipService:
    def __init__(self, persistence: PersistenceStore) -> None:
        self.persistence = persistence
        self.persistence.initialize()

    def add(self, membership: Membership, *, actor_member_type: str = "user", actor_role: str = "admin") -> Membership:
        if actor_member_type == "service_account" and membership.role in {"owner", "admin"}:
            raise PermissionError("service accounts cannot escalate roles")
        if actor_role not in {"owner", "admin"}:
            raise PermissionError("insufficient tenant role")
        self.persistence.put("memberships", membership.membership_id, membership.as_dict())
        return membership

    def list_for_tenant(self, tenant_id: str) -> list[Membership]:
        return [Membership.from_dict(item) for item in self.persistence.list_tenant("memberships", tenant_id)]

    def get(self, tenant_id: str, principal_id: str) -> Membership | None:
        item = self.persistence.get("memberships", f"{tenant_id}:{principal_id}")
        return Membership.from_dict(item) if item else None
