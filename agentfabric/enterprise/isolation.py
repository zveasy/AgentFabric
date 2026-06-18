"""Fail-closed tenant isolation helpers."""

from __future__ import annotations

from agentfabric.errors import AuthorizationError

from .tenant_context import TenantContext


TENANT_SCOPED_COLLECTIONS = {
    "agents",
    "identities",
    "certificates",
    "capabilities",
    "mesh_messages",
    "conversations",
    "workflows",
    "task_graphs",
    "checkpoints",
    "shared_context",
    "events",
    "reputation",
    "runtime_memory",
    "marketplace_installs",
    "billing_records",
    "audit_exports",
}


class TenantIsolation:
    def require_context(self, context: TenantContext | None) -> TenantContext:
        if context is None:
            raise AuthorizationError("tenant context is required")
        try:
            return context.require()
        except PermissionError as exc:
            raise AuthorizationError(str(exc)) from exc

    def assert_tenant(self, context: TenantContext | None, obj: dict[str, object]) -> None:
        ctx = self.require_context(context)
        object_tenant = obj.get("tenant_id")
        if object_tenant is None:
            raise AuthorizationError("tenant-scoped object is missing tenant_id")
        if object_tenant != ctx.tenant_id and not ctx.is_global_admin:
            raise AuthorizationError("cross-tenant access denied")

    def scoped_metadata(self, context: TenantContext) -> dict[str, object]:
        ctx = self.require_context(context)
        return {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": ctx.principal_id,
        }
