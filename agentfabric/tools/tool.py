"""Tenant-scoped governed tool."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from .tool_manifest import ToolManifest
from .tool_permission import ToolPermission


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class Tool:
    tenant_id: str
    organization_id: str
    created_by: str
    manifest: ToolManifest
    permission: ToolPermission
    tool_id: str = field(default_factory=lambda: f"tool-{uuid4().hex[:12]}")
    status: str = "active"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def validate(self) -> None:
        if not self.tenant_id or not self.organization_id:
            raise ValueError("tenant context is required")
        self.manifest.validate()
        if not self.permission.required_rbac_scope:
            raise ValueError("tool required_rbac_scope is required")

    def as_dict(self) -> dict[str, object]:
        return {
            "tool_id": self.tool_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "created_by": self.created_by,
            "manifest": self.manifest.as_dict(),
            "permission": self.permission.as_dict(),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "Tool":
        return cls(
            tool_id=str(value["tool_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            created_by=str(value.get("created_by", "")),
            manifest=ToolManifest.from_dict(dict(value["manifest"])),
            permission=ToolPermission.from_dict(dict(value["permission"])),
            status=str(value.get("status", "active")),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
            updated_at=datetime.fromisoformat(str(value["updated_at"])) if value.get("updated_at") else utc_now(),
        )
