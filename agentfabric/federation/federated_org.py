"""External federated organization records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class FederatedOrg:
    tenant_id: str
    organization_id: str
    remote_org_id: str
    name: str
    endpoint: str
    public_key: str
    created_by: str
    org_id: str = field(default_factory=lambda: f"fed-org-{uuid4().hex[:12]}")
    blocked: bool = False
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "org_id": self.org_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "remote_org_id": self.remote_org_id,
            "name": self.name,
            "endpoint": self.endpoint,
            "public_key": self.public_key,
            "created_by": self.created_by,
            "blocked": self.blocked,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "FederatedOrg":
        return cls(
            org_id=str(value["org_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            remote_org_id=str(value["remote_org_id"]),
            name=str(value["name"]),
            endpoint=str(value.get("endpoint", "")),
            public_key=str(value.get("public_key", "")),
            created_by=str(value.get("created_by", "")),
            blocked=bool(value.get("blocked", False)),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
            updated_at=datetime.fromisoformat(str(value["updated_at"])) if value.get("updated_at") else utc_now(),
        )
