"""Audit bundle manifest."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class AuditBundleManifest:
    tenant_id: str
    bundle_id: str = field(default_factory=lambda: f"audit-bundle-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=utc_now)
    schema_version: str = "generation-17"

    def as_dict(self) -> dict[str, object]:
        return {
            "bundle_id": self.bundle_id,
            "tenant_id": self.tenant_id,
            "created_at": self.created_at.isoformat(),
            "schema_version": self.schema_version,
        }
