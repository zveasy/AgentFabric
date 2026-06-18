"""Tenant enablement state for a registered connector."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class TenantConnector:
    tenant_id: str
    connector_id: str
    version: str
    enabled: bool
    enabled_by: str
    credential_ref: str | None = None
    policy_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def key(self) -> str:
        return f"{self.tenant_id}:{self.connector_id}"

    def set_enabled(
        self,
        enabled: bool,
        principal_id: str,
        *,
        credential_ref: str | None = None,
        policy_id: str | None = None,
    ) -> "TenantConnector":
        return replace(
            self,
            enabled=enabled,
            enabled_by=principal_id,
            credential_ref=credential_ref if credential_ref is not None else self.credential_ref,
            policy_id=policy_id if policy_id is not None else self.policy_id,
            updated_at=utc_now(),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "connector_id": self.connector_id,
            "version": self.version,
            "enabled": self.enabled,
            "enabled_by": self.enabled_by,
            "credential_ref": self.credential_ref,
            "policy_id": self.policy_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "TenantConnector":
        return cls(
            tenant_id=str(value["tenant_id"]),
            connector_id=str(value["connector_id"]),
            version=str(value["version"]),
            enabled=bool(value.get("enabled", False)),
            enabled_by=str(value.get("enabled_by", "")),
            credential_ref=str(value["credential_ref"]) if value.get("credential_ref") else None,
            policy_id=str(value["policy_id"]) if value.get("policy_id") else None,
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
            updated_at=datetime.fromisoformat(str(value["updated_at"])) if value.get("updated_at") else utc_now(),
        )
