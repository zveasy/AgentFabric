"""Connector registry and VEIL-mediated adapter execution."""

from __future__ import annotations

from agentfabric.cloud import CloudRuntime, RuntimeJob
from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError, NotFoundError, ValidationError
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore
from veil_client import AuditEventRequest, PolicyCheckRequest, SanitizeContextRequest, VeilClient

from .connector import Connector
from .connector_credentials import ConnectorCredentials
from .connector_manifest import ConnectorManifest
from .connector_policy import ConnectorPolicy
from .connector_result import ConnectorResult


CONNECTOR_JOB_TYPES = {
    "sync": "connector_sync",
    "search": "connector_search",
    "fetch": "connector_document_fetch",
    "webhook": "connector_webhook_handling",
    "event_ingestion": "connector_event_ingestion",
    "credential_rotation_check": "connector_credential_rotation_check",
}

SENSITIVE_KEYS = {"raw", "secret", "password", "token_value", "private_key", "credential"}


class ConnectorRegistry:
    def __init__(
        self,
        *,
        persistence: PersistenceStore,
        event_store: EventStore,
        veil_client: VeilClient,
        runtime: CloudRuntime | None = None,
    ) -> None:
        self.persistence = persistence
        self.event_store = event_store
        self.veil_client = veil_client
        self.runtime = runtime
        self.persistence.initialize()

    def register(
        self,
        *,
        ctx: TenantContext,
        manifest: ConnectorManifest,
        credentials: ConnectorCredentials,
        policy: ConnectorPolicy | None = None,
        connector_id: str | None = None,
    ) -> Connector:
        connector_kwargs = {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": ctx.principal_id,
            "manifest": manifest,
            "credentials": credentials,
            "policy": policy or ConnectorPolicy(),
        }
        if connector_id:
            connector_kwargs["connector_id"] = connector_id
        connector = Connector(
            **connector_kwargs,  # type: ignore[arg-type]
        )
        connector.validate()
        self.persistence.put("connectors", connector.connector_id, connector.as_dict())
        self.event_store.append("connector.registered", connector.connector_id, connector.as_dict())
        return connector

    def list(self, ctx: TenantContext) -> list[Connector]:
        return [Connector.from_dict(item) for item in self.persistence.list_tenant("connectors", ctx.tenant_id)]

    def get(self, ctx: TenantContext, connector_id: str) -> Connector:
        item = self.persistence.get("connectors", connector_id)
        if item is None:
            raise NotFoundError("connector not found")
        connector = Connector.from_dict(item)
        if connector.tenant_id != ctx.tenant_id and not ctx.is_global_admin:
            raise AuthorizationError("cross-tenant connector access denied")
        return connector

    def create_job(self, *, ctx: TenantContext, connector_id: str, operation: str, payload: dict[str, object]) -> RuntimeJob:
        connector = self.get(ctx, connector_id)
        self._assert_policy(connector, operation, payload)
        self._reject_raw(payload)
        job_type = CONNECTOR_JOB_TYPES.get(operation)
        if not job_type:
            raise ValidationError(f"unsupported connector operation: {operation}")
        job = RuntimeJob(
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
            created_by=ctx.principal_id,
            job_type=job_type,
            payload={
                "connector_id": connector.connector_id,
                "connector_type": connector.manifest.connector_type,
                "operation": operation,
                "request": self._tokenize_request(payload),
            },
        )
        if self.runtime is not None:
            created = self.runtime.submit(job)
        else:
            job.validate()
            self.persistence.put("runtime_jobs", job.job_id, job.as_dict())
            created = job
        self.event_store.append("connector.job.created", connector.connector_id, {**created.as_dict(), "tenant_id": ctx.tenant_id})
        return created

    def execute(self, *, ctx: TenantContext, connector_id: str, operation: str, payload: dict[str, object]) -> ConnectorResult:
        connector = self.get(ctx, connector_id)
        self._assert_policy(connector, operation, payload)
        self._reject_raw(payload)
        policy = self.veil_client.check_policy(
            PolicyCheckRequest(
                agent_id=f"connector:{connector.connector_id}",
                action=f"connector.{operation}",
                payload={
                    "tenant_id": ctx.tenant_id,
                    "connector_id": connector.connector_id,
                    "connector_type": connector.manifest.connector_type,
                    "data_class": payload.get("data_class"),
                },
            )
        )
        if not policy.allowed:
            self.event_store.append(
                "connector.policy.denied",
                connector.connector_id,
                {"tenant_id": ctx.tenant_id, "operation": operation, "reason": policy.reason},
            )
            raise AuthorizationError(policy.reason or "VEIL policy denied connector operation")
        sanitized = self.veil_client.sanitize_context(
            SanitizeContextRequest(
                agent_id=f"connector:{connector.connector_id}",
                tenant_id=ctx.tenant_id,
                context=dict(payload),
            )
        )
        self._reject_raw(sanitized.sanitized_context)
        audit = self.veil_client.create_audit_event(
            AuditEventRequest(
                agent_id=f"connector:{connector.connector_id}",
                event_type=f"connector.{operation}",
                payload={"tenant_id": ctx.tenant_id, "connector_id": connector.connector_id},
            )
        )
        result = ConnectorResult(
            connector_id=connector.connector_id,
            tenant_id=ctx.tenant_id,
            operation=operation,
            sanitized_payload=sanitized.sanitized_context,
            veil_audit_id=audit.event_id,
            token_refs=tuple(str(item) for item in sanitized.sanitized_context.get("veil_token_refs", ())),
        )
        self.persistence.put("connector_results", result.as_dict()["result_id"], result.as_dict())
        self.event_store.append("connector.operation.completed", connector.connector_id, result.as_dict())
        return result

    def health(self, *, ctx: TenantContext, connector_id: str) -> dict[str, object]:
        connector = self.get(ctx, connector_id)
        return {
            "connector_id": connector.connector_id,
            "tenant_id": connector.tenant_id,
            "status": connector.status,
            "connector_type": connector.manifest.connector_type,
            "credential_ref_present": bool(connector.credentials.credential_ref),
            "policy": connector.policy.as_dict(),
        }

    def _assert_policy(self, connector: Connector, operation: str, payload: dict[str, object]) -> None:
        data_class = str(payload["data_class"]) if payload.get("data_class") else None
        if not connector.policy.allows(operation, data_class):
            raise AuthorizationError("connector policy denied operation")

    def _reject_raw(self, payload: object) -> None:
        if _contains_sensitive_key(payload):
            raise ValidationError("raw connector payload values are not allowed")

    def _tokenize_request(self, payload: dict[str, object]) -> dict[str, object]:
        return {key: value for key, value in payload.items() if key not in SENSITIVE_KEYS}


def _contains_sensitive_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                return True
            if _contains_sensitive_key(item):
                return True
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False
