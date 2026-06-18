"""Tool registry and governed execution service."""

from __future__ import annotations

from agentfabric.cloud import CloudRuntime, RuntimeJob
from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError, NotFoundError
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore
from veil_client import AuditEventRequest, PolicyCheckRequest, SanitizeContextRequest, VeilClient

from .tool import Tool
from .tool_manifest import ToolManifest
from .tool_permission import ToolPermission
from .tool_result import ToolResult
from .tool_router import ToolRouter


class ToolRegistry:
    def __init__(
        self,
        *,
        persistence: PersistenceStore,
        event_store: EventStore,
        veil_client: VeilClient,
        router: ToolRouter,
        runtime: CloudRuntime | None = None,
    ) -> None:
        self.persistence = persistence
        self.event_store = event_store
        self.veil_client = veil_client
        self.router = router
        self.runtime = runtime
        self.persistence.initialize()

    def register(
        self,
        *,
        ctx: TenantContext,
        manifest: ToolManifest,
        permission: ToolPermission,
        tool_id: str | None = None,
    ) -> Tool:
        kwargs = {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": ctx.principal_id,
            "manifest": manifest,
            "permission": permission,
        }
        if tool_id:
            kwargs["tool_id"] = tool_id
        tool = Tool(**kwargs)  # type: ignore[arg-type]
        tool.validate()
        self.persistence.put("tools", tool.tool_id, tool.as_dict())
        self.event_store.append("tool.registered", tool.tool_id, tool.as_dict())
        return tool

    def list(self, ctx: TenantContext) -> list[Tool]:
        return [Tool.from_dict(item) for item in self.persistence.list_tenant("tools", ctx.tenant_id)]

    def get(self, ctx: TenantContext, tool_id: str) -> Tool:
        item = self.persistence.get("tools", tool_id)
        if item is None:
            raise NotFoundError("tool not found")
        tool = Tool.from_dict(item)
        if tool.tenant_id != ctx.tenant_id and not ctx.is_global_admin:
            raise AuthorizationError("cross-tenant tool access denied")
        return tool

    def execute(self, *, ctx: TenantContext, tool_id: str, payload: dict[str, object], governance_approved: bool = False) -> tuple[ToolResult, RuntimeJob | None]:
        tool = self.get(ctx, tool_id)
        self._enforce(ctx, tool, payload, governance_approved)
        output = self.router.route(ctx=ctx, tool=tool, payload=payload)
        sanitized = self.veil_client.sanitize_context(
            SanitizeContextRequest(
                agent_id=f"tool:{tool.tool_id}",
                tenant_id=ctx.tenant_id,
                context=output,
            )
        )
        classification = str(sanitized.sanitized_context.get("classification", "internal"))
        if classification not in tool.permission.allowed_output_classifications:
            raise AuthorizationError("tool output classification is not allowed")
        audit = self.veil_client.create_audit_event(
            AuditEventRequest(
                agent_id=f"tool:{tool.tool_id}",
                event_type="tool.executed",
                payload={"tenant_id": ctx.tenant_id, "tool_id": tool.tool_id, "tool_type": tool.manifest.tool_type},
            )
        )
        result = ToolResult(
            tool_id=tool.tool_id,
            tenant_id=ctx.tenant_id,
            output=sanitized.sanitized_context,
            classification=classification,
            veil_audit_id=audit.event_id,
            persisted=tool.permission.result_persistence_allowed,
        )
        if tool.permission.result_persistence_allowed:
            self.persistence.put("tool_results", result.execution_id, result.as_dict())
        job = self._create_job(ctx, tool, result, payload)
        self.event_store.append("tool.executed", result.execution_id, result.as_dict())
        return result, job

    def get_execution(self, ctx: TenantContext, execution_id: str) -> ToolResult:
        item = self.persistence.get("tool_results", execution_id)
        if item is None:
            raise NotFoundError("tool execution not found")
        result = ToolResult.from_dict(item)
        if result.tenant_id != ctx.tenant_id and not ctx.is_global_admin:
            raise AuthorizationError("cross-tenant tool execution access denied")
        return result

    def health(self, *, ctx: TenantContext, tool_id: str) -> dict[str, object]:
        tool = self.get(ctx, tool_id)
        return {
            "tool_id": tool.tool_id,
            "tenant_id": tool.tenant_id,
            "status": tool.status,
            "tool_type": tool.manifest.tool_type,
            "permission": tool.permission.as_dict(),
        }

    def _enforce(self, ctx: TenantContext, tool: Tool, payload: dict[str, object], governance_approved: bool) -> None:
        if tool.permission.required_tenant_context and not ctx.tenant_id:
            raise AuthorizationError("tool execution requires tenant context")
        if tool.permission.required_rbac_scope not in set(ctx.roles):
            raise AuthorizationError("tool execution missing required RBAC scope")
        if tool.permission.governance_approval_required and not governance_approved:
            self.event_store.append("tool.approval.required", tool.tool_id, {"tenant_id": ctx.tenant_id, "tool_id": tool.tool_id})
            raise AuthorizationError("governance approval is required")
        if tool.permission.required_veil_policy_check:
            policy = self.veil_client.check_policy(
                PolicyCheckRequest(
                    agent_id=f"tool:{tool.tool_id}",
                    action=f"tool.execute.{tool.manifest.tool_type}",
                    payload={"tenant_id": ctx.tenant_id, "tool_id": tool.tool_id, "payload": payload},
                )
            )
            if not policy.allowed:
                self.event_store.append("tool.policy.denied", tool.tool_id, {"tenant_id": ctx.tenant_id, "reason": policy.reason})
                raise AuthorizationError(policy.reason or "VEIL policy denied tool execution")

    def _create_job(self, ctx: TenantContext, tool: Tool, result: ToolResult, payload: dict[str, object]) -> RuntimeJob | None:
        if self.runtime is None:
            return None
        job = RuntimeJob(
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
            created_by=ctx.principal_id,
            job_type="tool_execution",
            payload={
                "tool_id": tool.tool_id,
                "execution_id": result.execution_id,
                "tool_type": tool.manifest.tool_type,
                "agent_id": str(payload.get("agent_id", ctx.principal_id)),
            },
        )
        created = self.runtime.submit(job)
        self.event_store.append("tool.job.created", tool.tool_id, created.as_dict())
        return created
