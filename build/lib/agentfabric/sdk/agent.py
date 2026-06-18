"""
Agent base class: implement run() and optional tools; validation against manifest.
"""

from __future__ import annotations

from typing import Any, Awaitable
from agentfabric.runtime.manifest import Manifest, load_manifest


class Agent:
    """
    Base class for AgentFabric agents. Subclass and implement run().
    Declare tools in the manifest; the runtime will route tool calls to the
    tool router. Use run_tool() from within run() if you have access to a
    tool router reference (e.g. injected by the runtime).
    """

    def __init__(self, manifest: Manifest | None = None, manifest_path: str | None = None) -> None:
        if manifest is not None:
            self._manifest = manifest
        elif manifest_path:
            self._manifest = load_manifest(manifest_path)
        else:
            raise ValueError("Provide manifest or manifest_path")

    @property
    def manifest(self) -> Manifest:
        return self._manifest

    def run(self, request: dict[str, Any]) -> dict[str, Any] | Awaitable[dict[str, Any]]:
        """
        Execute the agent for the given run request. Request contains type, id,
        agent_id, input, options (timeout_seconds, max_tool_calls, correlation_id).
        Return a run_response dict: type, id, request_id, success, output, error, events.
        """
        raise NotImplementedError("Subclass must implement run()")

    @staticmethod
    def run_response(
        request_id: str,
        success: bool,
        output: dict[str, Any] | None = None,
        error: dict[str, str] | None = None,
        events: list | None = None,
    ) -> dict[str, Any]:
        """Build a protocol run_response dict."""
        import uuid
        return {
            "type": "run_response",
            "id": f"resp-{uuid.uuid4().hex[:12]}",
            "request_id": request_id,
            "success": success,
            "output": output,
            "error": error,
            "events": events or [],
        }

    def run_tool_sync(self, name: str, arguments: dict[str, Any], tool_router: Any, request_id: str) -> Any:
        """Synchronous helper to execute a tool via the runtime and return data or raise."""
        import asyncio
        call = {"type": "tool_call", "id": f"call-{name}", "name": name, "arguments": arguments}
        result = asyncio.run(tool_router.execute(call, self._manifest, request_id))
        if not result.get("success"):
            raise RuntimeError(result.get("error", {}).get("message", "Tool call failed"))
        return result.get("data")
