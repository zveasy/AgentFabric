"""Governed tool execution router."""

from __future__ import annotations

from agentfabric.audit_bundle import AuditBundleExporter
from agentfabric.connectors import ConnectorRegistry
from agentfabric.enterprise import TenantContext
from agentfabric.errors import ValidationError
from agentfabric.intelligence import CodeIntelligence, DocumentIntelligence, EmailIntelligence, TicketIntelligence

from .tool import Tool


SENSITIVE_KEYS = {"raw", "secret", "password", "token_value", "private_key", "credential"}


class ToolRouter:
    def __init__(
        self,
        *,
        connector_registry: ConnectorRegistry | None = None,
        audit_exporter: AuditBundleExporter | None = None,
    ) -> None:
        self.connector_registry = connector_registry
        self.audit_exporter = audit_exporter

    def route(self, *, ctx: TenantContext, tool: Tool, payload: dict[str, object]) -> dict[str, object]:
        self._reject_raw(payload)
        tool_type = tool.manifest.tool_type
        if tool_type == "connector_search":
            return self._connector(ctx, tool, payload, "search")
        if tool_type == "connector_fetch":
            return self._connector(ctx, tool, payload, "fetch")
        if tool_type == "document_summary":
            return DocumentIntelligence().analyze(payload)
        if tool_type == "ticket_analysis":
            return TicketIntelligence().analyze(payload)
        if tool_type == "email_analysis":
            return EmailIntelligence().analyze(payload)
        if tool_type == "code_repository_review":
            return CodeIntelligence().review(payload)
        if tool_type == "audit_bundle_generation":
            if self.audit_exporter is None:
                raise ValidationError("audit bundle exporter is not configured")
            return {"audit_bundle": self.audit_exporter.export(ctx.tenant_id).as_dict(), "classification": "internal"}
        if tool_type == "governance_proposal_creation":
            return {
                "proposal_request": {
                    "tenant_id": ctx.tenant_id,
                    "action_type": payload.get("action_type", "new_workflow_execution"),
                    "veil_token_refs": list(payload.get("veil_token_refs", ())),
                },
                "classification": "internal",
            }
        if tool_type == "marketplace_package_verification":
            manifest = dict(payload.get("manifest", {}))
            return {
                "verification": {
                    "ok": bool(manifest.get("package_id") and manifest.get("version")),
                    "package_id": manifest.get("package_id"),
                    "signature_checked": bool(payload.get("signature") or payload.get("signature_ref")),
                },
                "classification": "internal",
            }
        raise ValidationError(f"unsupported tool type: {tool_type}")

    def _connector(self, ctx: TenantContext, tool: Tool, payload: dict[str, object], operation: str) -> dict[str, object]:
        if self.connector_registry is None:
            raise ValidationError("connector registry is not configured")
        connector_id = str(payload.get("connector_id", ""))
        if not connector_id:
            raise ValidationError("connector_id is required")
        result = self.connector_registry.execute(ctx=ctx, connector_id=connector_id, operation=operation, payload=payload)
        return {
            "connector_result_id": result.as_dict()["result_id"],
            "sanitized_payload": result.sanitized_payload,
            "veil_audit_id": result.veil_audit_id,
            "veil_token_refs": list(result.token_refs),
            "classification": "internal",
            "tool_id": tool.tool_id,
        }

    def _reject_raw(self, value: object) -> None:
        if _contains_sensitive_key(value):
            raise ValidationError("raw tool payload values are not allowed")


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
