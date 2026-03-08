"""Permission-aware tool routing."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable

from agentfabric.phase1.manifest import AgentManifest
from agentfabric.phase1.protocol import ProtocolEnvelope
from agentfabric.phase1.security import PermissionEnforcer


ToolHandler = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    required_permission: str
    handler: ToolHandler


class ToolRouter:
    """Centralized tool routing with manifest permission checks."""

    def __init__(self, permission_enforcer: PermissionEnforcer | None = None) -> None:
        self._permission_enforcer = permission_enforcer or PermissionEnforcer()
        self._tools: dict[str, RegisteredTool] = {}

    def register_tool(self, name: str, required_permission: str, handler: ToolHandler) -> None:
        self._tools[name] = RegisteredTool(name=name, required_permission=required_permission, handler=handler)

    def invoke(self, manifest: AgentManifest, tool_name: str, args: dict[str, Any], correlation_id: str) -> ProtocolEnvelope:
        tool = self._tools[tool_name]
        self._permission_enforcer.check(manifest, tool.required_permission)
        start = monotonic()
        result = tool.handler(args)
        duration_seconds = monotonic() - start
        return ProtocolEnvelope(
            protocol_version="v1",
            message_type="tool_result",
            correlation_id=correlation_id,
            payload={
                "tool_name": tool_name,
                "result": result,
                "duration_seconds": round(duration_seconds, 6),
            },
        )
