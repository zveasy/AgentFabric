"""Versioned connector registry and tenant enablement."""

from __future__ import annotations

from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError, ConflictError, NotFoundError
from agentfabric.persistence import PersistenceStore

from .audit import ConnectorAudit
from .connector import TenantConnector
from .manifest import ConnectorManifest
from .policy import ConnectorExecutionPolicy


class ConnectorRegistry:
    def __init__(self, persistence: PersistenceStore, audit: ConnectorAudit) -> None:
        self.persistence = persistence
        self.audit = audit
        self.persistence.initialize()

    def register(self, manifest: ConnectorManifest, *, tenant_id: str, created_by: str) -> ConnectorManifest:
        manifest.validate()
        key = f"{manifest.connector_id}:{manifest.version}"
        existing = self.persistence.get("enterprise_connector_manifests", key)
        if existing and existing != manifest.as_dict():
            raise ConflictError("connector version already exists with different manifest")
        record = {**manifest.as_dict(), "tenant_id": tenant_id, "created_by": created_by}
        self.persistence.put("enterprise_connector_manifests", key, record)
        self.persistence.put("enterprise_connector_latest", manifest.connector_id, record)
        self.audit.emit("connector.registered", manifest.connector_id, record)
        return manifest

    def list(self, ctx: TenantContext) -> list[dict[str, object]]:
        return self.persistence.list_tenant("enterprise_connector_manifests", ctx.tenant_id)

    def get(self, ctx: TenantContext, connector_id: str, version: str | None = None) -> ConnectorManifest:
        value = self.persistence.get(
            "enterprise_connector_manifests" if version else "enterprise_connector_latest",
            f"{connector_id}:{version}" if version else connector_id,
        )
        if value is None:
            raise NotFoundError("connector not found")
        if value.get("tenant_id") != ctx.tenant_id and not ctx.is_global_admin:
            raise AuthorizationError("cross-tenant connector access denied")
        return ConnectorManifest.from_dict(value)

    def enable(
        self,
        ctx: TenantContext,
        connector_id: str,
        *,
        version: str | None,
        credential_ref: str,
        policy: ConnectorExecutionPolicy,
    ) -> TenantConnector:
        manifest = self.get(ctx, connector_id, version)
        policy.validate()
        if policy.tenant_id != ctx.tenant_id:
            raise AuthorizationError("cross-tenant connector policy denied")
        state = TenantConnector(
            tenant_id=ctx.tenant_id,
            connector_id=connector_id,
            version=manifest.version,
            enabled=True,
            enabled_by=ctx.principal_id,
            credential_ref=credential_ref,
            policy_id=policy.policy_id,
        )
        self.persistence.put("enterprise_connector_policies", f"{ctx.tenant_id}:{policy.policy_id}", policy.as_dict())
        self.persistence.put("enterprise_connector_enablement", state.key, state.as_dict())
        self.audit.emit("connector.enabled", connector_id, state.as_dict())
        return state

    def disable(self, ctx: TenantContext, connector_id: str) -> TenantConnector:
        state = self.state(ctx, connector_id).set_enabled(False, ctx.principal_id)
        self.persistence.put("enterprise_connector_enablement", state.key, state.as_dict())
        self.audit.emit("connector.disabled", connector_id, state.as_dict())
        return state

    def state(self, ctx: TenantContext, connector_id: str) -> TenantConnector:
        value = self.persistence.get("enterprise_connector_enablement", f"{ctx.tenant_id}:{connector_id}")
        if value is None:
            raise NotFoundError("connector is not enabled for tenant")
        state = TenantConnector.from_dict(value)
        if state.tenant_id != ctx.tenant_id:
            raise AuthorizationError("cross-tenant connector state denied")
        return state

    def policy(self, ctx: TenantContext, policy_id: str) -> ConnectorExecutionPolicy:
        value = self.persistence.get("enterprise_connector_policies", f"{ctx.tenant_id}:{policy_id}")
        if value is None:
            raise NotFoundError("connector policy not found")
        return ConnectorExecutionPolicy.from_dict(value)
