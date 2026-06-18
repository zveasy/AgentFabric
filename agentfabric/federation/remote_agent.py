"""Federated remote agent catalog entries."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from .remote_capability import RemoteCapability


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class RemoteAgent:
    tenant_id: str
    organization_id: str
    remote_org_id: str
    remote_agent_id: str
    name: str
    capabilities: tuple[RemoteCapability, ...]
    reputation_score: float = 1.0
    publisher_id: str = ""
    blocked: bool = False
    catalog_id: str = field(default_factory=lambda: f"remote-agent-{uuid4().hex[:12]}")
    imported_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "catalog_id": self.catalog_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "remote_org_id": self.remote_org_id,
            "remote_agent_id": self.remote_agent_id,
            "name": self.name,
            "capabilities": [capability.as_dict() for capability in self.capabilities],
            "reputation_score": self.reputation_score,
            "publisher_id": self.publisher_id,
            "blocked": self.blocked,
            "imported_at": self.imported_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "RemoteAgent":
        return cls(
            catalog_id=str(value["catalog_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            remote_org_id=str(value["remote_org_id"]),
            remote_agent_id=str(value["remote_agent_id"]),
            name=str(value["name"]),
            capabilities=tuple(RemoteCapability.from_dict(item) for item in value.get("capabilities", ())),
            reputation_score=float(value.get("reputation_score", 1.0)),
            publisher_id=str(value.get("publisher_id", "")),
            blocked=bool(value.get("blocked", False)),
            imported_at=datetime.fromisoformat(str(value["imported_at"])) if value.get("imported_at") else utc_now(),
        )
