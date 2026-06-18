"""Tenant entitlement record."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class Entitlement:
    tenant_id: str
    package_id: str
    version: str
    license_type: str
    active: bool = True
    expires_at: datetime | None = None
    entitlement_id: str = field(default_factory=lambda: f"ent-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "entitlement_id": self.entitlement_id,
            "tenant_id": self.tenant_id,
            "package_id": self.package_id,
            "version": self.version,
            "license_type": self.license_type,
            "active": self.active,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "Entitlement":
        return cls(
            entitlement_id=str(value["entitlement_id"]),
            tenant_id=str(value["tenant_id"]),
            package_id=str(value["package_id"]),
            version=str(value["version"]),
            license_type=str(value["license_type"]),
            active=bool(value.get("active", True)),
            expires_at=datetime.fromisoformat(str(value["expires_at"])) if value.get("expires_at") else None,
            created_at=datetime.fromisoformat(str(value["created_at"])),
        )
