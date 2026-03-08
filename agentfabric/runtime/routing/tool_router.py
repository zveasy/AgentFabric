"""
Tool router: route tool calls from agents through a single layer that enforces
permissions and returns results in the protocol format.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Awaitable

from agentfabric.runtime.manifest import Manifest


ToolCall = dict[str, Any]
ToolResult = dict[str, Any]

# (tool_name, arguments) -> result data or raise
ToolExecutor = Callable[[str, dict[str, Any]], Any] | Callable[
    [str, dict[str, Any]], Awaitable[Any]
]


class ToolRouter:
    """
    Validates tool calls against the agent manifest and routes them to
    registered executors. Returns protocol-format tool results.
    """

    def __init__(self) -> None:
        self._executors: dict[str, ToolExecutor] = {}

    def register_tool(self, name: str, executor: ToolExecutor) -> None:
        """Register an executor for a tool name."""
        self._executors[name] = executor

    def unregister_tool(self, name: str) -> bool:
        if name in self._executors:
            del self._executors[name]
            return True
        return False

    def can_execute(self, manifest: Manifest, tool_name: str) -> tuple[bool, str | None]:
        """
        Return (allowed, error_message). If allowed is False, error_message explains why.
        """
        if not manifest.allows_tool(tool_name):
            return False, f"Tool '{tool_name}' not in manifest tools"
        if tool_name not in self._executors:
            return False, f"Tool '{tool_name}' has no registered executor"
        return True, None

    async def execute(
        self,
        call: ToolCall,
        manifest: Manifest,
        request_id: str,
    ) -> ToolResult:
        """
        Validate the tool call against manifest and execute. Returns protocol ToolResult.
        """
        call_id = call.get("id", f"call-{uuid.uuid4().hex[:12]}")
        name = call.get("name")
        arguments = call.get("arguments") or {}

        if not name:
            return _tool_result(call_id, request_id, False, None, "invalid_tool", "Missing tool name")

        allowed, err = self.can_execute(manifest, name)
        if not allowed:
            return _tool_result(
                call_id, request_id, False, None, "permission_denied", err or "Denied"
            )

        executor = self._executors[name]
        try:
            if hasattr(executor, "__call__"):
                import asyncio
                if asyncio.iscoroutinefunction(executor):
                    data = await executor(name, arguments)
                else:
                    data = executor(name, arguments)
            else:
                data = executor(name, arguments)
            return _tool_result(call_id, request_id, True, data, None, None)
        except Exception as e:
            return _tool_result(
                call_id, request_id, False, None, "tool_error", str(e)
            )


def _tool_result(
    call_id: str,
    request_id: str,
    success: bool,
    data: Any,
    error_code: str | None,
    error_message: str | None,
) -> ToolResult:
    return {
        "type": "tool_result",
        "id": f"result-{uuid.uuid4().hex[:12]}",
        "call_id": call_id,
        "request_id": request_id,
        "success": success,
        "data": data,
        "error": {"code": error_code, "message": error_message} if not success else None,
    }
