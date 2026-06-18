"""Tenant context required for enterprise-safe operations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    organization_id: str
    principal_id: str
    roles: tuple[str, ...] = ()
    is_global_admin: bool = False

    def require(self) -> "TenantContext":
        if not self.tenant_id or not self.organization_id or not self.principal_id:
            raise PermissionError("tenant context is required")
        return self

    def as_metadata(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "created_by": self.principal_id,
        }
