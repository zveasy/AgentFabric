"""Secure connector execution control plane."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from agentfabric.persistence import PersistenceStore
from veil_client import AuditEventRequest, PolicyCheckRequest, SanitizeContextRequest, VeilClient

from .audit import ConnectorAudit
from .credential_vault import CredentialReference, CredentialVault
from .execution import ConnectorExecution
from .manifest import ConnectorManifest
from .permissions import permission_for, require_permissions
from .policy import ConnectorExecutionPolicy
from .registry import ConnectorRegistry
from .sandbox import ConnectorSandbox


class ConnectorExecutionService:
    def __init__(
        self,
        *,
        persistence: PersistenceStore,
        registry: ConnectorRegistry,
        vault: CredentialVault,
        audit: ConnectorAudit,
        veil_client: VeilClient | None,
        production: bool = False,
        sandbox: ConnectorSandbox | None = None,
        adapter: Callable[[ConnectorManifest, str, dict[str, object], str], dict[str, object]] | None = None,
    ) -> None:
        self.persistence = persistence
        self.registry = registry
        self.vault = vault
        self.audit = audit
        self.veil_client = veil_client
        self.production = production
        self.sandbox = sandbox or ConnectorSandbox()
        self.adapter = adapter or _default_adapter

    def execute(
        self,
        *,
        ctx: TenantContext,
        connector_id: str,
        agent_id: str,
        action: str,
        payload: dict[str, object],
        agent_permissions: set[str],
        package_trust_score: float = 1.0,
    ) -> ConnectorExecution:
        ctx.require()
        self.audit.emit(
            "connector.execution.requested",
            connector_id,
            {"tenant_id": ctx.tenant_id, "connector_id": connector_id, "agent_id": agent_id, "action": action},
        )
        try:
            state = self.registry.state(ctx, connector_id)
            if not state.enabled:
                raise AuthorizationError("connector is disabled")
            manifest = self.registry.get(ctx, connector_id, state.version)
            if action not in manifest.supported_actions:
                raise AuthorizationError("connector action is not supported")
            required = {permission_for(manifest.connector_type, action)}
            require_permissions(agent_permissions, required)
            if not state.credential_ref:
                raise AuthorizationError("connector credential is not configured")
            credential_id = _credential_id(state.credential_ref)
            credential = self.vault.get(ctx.tenant_id, credential_id)
            if credential.connector_id != connector_id:
                raise AuthorizationError("credential is not scoped to this connector")
            policy = self.registry.policy(ctx, state.policy_id or "")
            decision = policy.decide(
                agent_id=agent_id,
                connector_id=connector_id,
                action=action,
                credential_type=credential.credential_type,
                risk_level=manifest.risk_level,
                package_trust_score=package_trust_score,
            )
            if not decision.allowed:
                raise AuthorizationError("; ".join(decision.reasons))
            self._enforce_rate_limit(ctx.tenant_id, connector_id, manifest)
            self.sandbox.validate_request(
                payload,
                allowed_domains=manifest.allowed_domains,
                allowed_methods=manifest.allowed_http_methods,
            )
            sanitized = self._veil_authorize_and_sanitize(ctx, manifest, agent_id, action, payload, policy)
            secret = self.vault.resolve(ctx.tenant_id, credential_id)
            response = self.adapter(manifest, action, sanitized, secret)
            self.sandbox.validate_response(response)
            audit_ref = self._veil_audit(ctx, connector_id, agent_id, action)
            execution = ConnectorExecution(
                tenant_id=ctx.tenant_id,
                connector_id=connector_id,
                connector_version=manifest.version,
                agent_id=agent_id,
                action=action,
                status="completed",
                normalized_result={"connector_id": connector_id, "action": action, "data": response},
                credential_ref=credential.reference_id,
                policy_decision=decision.as_dict(),
                veil_audit_ref=audit_ref,
            )
            self.persistence.put("enterprise_connector_executions", execution.execution_id, execution.as_dict())
            self.audit.emit("connector.execution.allowed", connector_id, execution.as_dict())
            self.audit.emit("connector.execution.completed", connector_id, execution.as_dict())
            return execution
        except (AuthorizationError, PermissionError, ValueError, ValidationError, ConflictError, NotFoundError) as exc:
            event_type = "connector.execution.denied" if isinstance(exc, (AuthorizationError, PermissionError, NotFoundError)) else "connector.execution.failed"
            denial = {
                "tenant_id": ctx.tenant_id,
                "connector_id": connector_id,
                "agent_id": agent_id,
                "action": action,
                "reason": str(exc),
            }
            self.persistence.put(
                "enterprise_connector_denials",
                f"{connector_id}:{datetime.now(tz=timezone.utc).timestamp()}",
                denial,
            )
            self.audit.emit(event_type, connector_id, denial)
            if isinstance(exc, PermissionError):
                raise AuthorizationError(str(exc)) from exc
            if isinstance(exc, ValueError):
                raise ValidationError(str(exc)) from exc
            raise
        except Exception as exc:
            failure = {
                "tenant_id": ctx.tenant_id,
                "connector_id": connector_id,
                "agent_id": agent_id,
                "action": action,
                "reason": "connector execution failed",
            }
            self.persistence.put(
                "enterprise_connector_denials",
                f"{connector_id}:{datetime.now(tz=timezone.utc).timestamp()}",
                failure,
            )
            self.audit.emit("connector.execution.failed", connector_id, failure)
            raise ValidationError("connector execution failed") from exc

    def _veil_authorize_and_sanitize(
        self,
        ctx: TenantContext,
        manifest: ConnectorManifest,
        agent_id: str,
        action: str,
        payload: dict[str, object],
        policy: ConnectorExecutionPolicy,
    ) -> dict[str, object]:
        if self.veil_client is None:
            if self.production or policy.require_veil:
                raise AuthorizationError("VEIL policy service is unavailable")
            return dict(payload)
        try:
            decision = self.veil_client.check_policy(
                PolicyCheckRequest(
                    agent_id=agent_id,
                    action=f"connector.{manifest.connector_type}.{action}",
                    payload={"tenant_id": ctx.tenant_id, "connector_id": manifest.connector_id},
                )
            )
            if not decision.allowed:
                raise AuthorizationError(decision.reason or "VEIL denied connector execution")
            sanitized = self.veil_client.sanitize_context(
                SanitizeContextRequest(agent_id=agent_id, tenant_id=ctx.tenant_id, context=dict(payload))
            ).sanitized_context
            self.sandbox.validate_request(
                sanitized,
                allowed_domains=manifest.allowed_domains,
                allowed_methods=manifest.allowed_http_methods,
            )
            return sanitized
        except AuthorizationError:
            raise
        except Exception as exc:
            if self.production or policy.require_veil:
                raise AuthorizationError("VEIL policy service is unavailable") from exc
            return dict(payload)

    def _veil_audit(self, ctx: TenantContext, connector_id: str, agent_id: str, action: str) -> str | None:
        if self.veil_client is None:
            return None
        response = self.veil_client.create_audit_event(
            AuditEventRequest(
                agent_id=agent_id,
                event_type="connector.execution.completed",
                payload={"tenant_id": ctx.tenant_id, "connector_id": connector_id, "action": action},
            )
        )
        return response.event_id

    def _enforce_rate_limit(self, tenant_id: str, connector_id: str, manifest: ConnectorManifest) -> None:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=1)
        recent = [
            item for item in self.persistence.list_tenant("enterprise_connector_executions", tenant_id)
            if item.get("connector_id") == connector_id
            and datetime.fromisoformat(str(item["timestamp"])) >= cutoff
        ]
        if len(recent) >= int(manifest.rate_limits["requests_per_minute"]):
            raise AuthorizationError("connector rate limit exceeded")


class EnterpriseConnectorService:
    def __init__(
        self,
        *,
        persistence: PersistenceStore,
        event_store,
        veil_client: VeilClient | None,
        production: bool = False,
    ) -> None:
        self.audit = ConnectorAudit(event_store)
        self.registry = ConnectorRegistry(persistence, self.audit)
        self.vault = CredentialVault(persistence)
        self.execution = ConnectorExecutionService(
            persistence=persistence,
            registry=self.registry,
            vault=self.vault,
            audit=self.audit,
            veil_client=veil_client,
            production=production,
        )

    def create_credential(self, ctx: TenantContext, payload: dict[str, object]) -> CredentialReference:
        reference = self.vault.create(
            tenant_id=ctx.tenant_id,
            connector_id=str(payload["connector_id"]),
            credential_type=str(payload.get("credential_type", "api_key")),
            created_by=ctx.principal_id,
            secret=str(payload["secret"]),
        )
        self.audit.emit("credential.created", reference.credential_id, reference.as_dict())
        return reference

    def rotate_credential(self, ctx: TenantContext, credential_id: str, secret: str) -> CredentialReference:
        reference = self.vault.rotate(ctx.tenant_id, credential_id, secret)
        self.audit.emit("credential.rotated", credential_id, reference.as_dict())
        return reference

    def revoke_credential(self, ctx: TenantContext, credential_id: str) -> CredentialReference:
        reference = self.vault.revoke(ctx.tenant_id, credential_id)
        self.audit.emit("credential.revoked", credential_id, reference.as_dict())
        return reference


def _credential_id(reference: str) -> str:
    parts = reference.split(":")
    if len(parts) < 3 or parts[0] != "vault-ref":
        raise AuthorizationError("invalid credential reference")
    return parts[1]


def _default_adapter(
    manifest: ConnectorManifest,
    action: str,
    payload: dict[str, object],
    credential: str,
) -> dict[str, object]:
    if not credential:
        raise AuthorizationError("credential material unavailable")
    return {
        "connector_type": manifest.connector_type,
        "action": action,
        "payload": dict(payload),
    }
