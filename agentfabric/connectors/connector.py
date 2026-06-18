"""Tenant-scoped enterprise connector record."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from .connector_credentials import ConnectorCredentials
from .connector_manifest import ConnectorManifest
from .connector_policy import ConnectorPolicy


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class Connector:
    tenant_id: str
    organization_id: str
    created_by: str
    manifest: ConnectorManifest
    credentials: ConnectorCredentials
    policy: ConnectorPolicy = field(default_factory=ConnectorPolicy)
    connector_id: str = field(default_factory=lambda: f"connector-{uuid4().hex[:12]}")
    status: str = "active"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def validate(self) -> None:
        if not self.tenant_id or not self.organization_id:
            raise ValueError("tenant context is required")
        self.manifest.validate()
        self.credentials.validate()

    def as_dict(self) -> dict[str, object]:
        return {
            "connector_id": self.connector_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "created_by": self.created_by,
            "manifest": self.manifest.as_dict(),
            "credentials": self.credentials.as_dict(),
            "policy": self.policy.as_dict(),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "Connector":
        return cls(
            connector_id=str(value["connector_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            created_by=str(value.get("created_by", "")),
            manifest=ConnectorManifest.from_dict(dict(value["manifest"])),
            credentials=ConnectorCredentials.from_dict(dict(value["credentials"])),
            policy=ConnectorPolicy.from_dict(dict(value.get("policy", {}))),
            status=str(value.get("status", "active")),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
            updated_at=datetime.fromisoformat(str(value["updated_at"])) if value.get("updated_at") else utc_now(),
        )
