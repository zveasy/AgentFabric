"""
Orchestrator: load agents from manifest, route run requests, handle timeouts and cancellation.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable, Awaitable

from agentfabric.runtime.manifest import Manifest


RunRequest = dict[str, Any]
RunResponse = dict[str, Any]
ToolCall = dict[str, Any]
ToolResult = dict[str, Any]

# Type alias for agent run: (request) -> response (sync or async)
AgentRunner = Callable[[RunRequest], RunResponse] | Callable[[RunRequest], Awaitable[RunResponse]]


class Orchestrator:
    """
    Loads agents from manifests and routes run requests to the correct agent.
    Handles timeouts and cancellation.
    """

    PROTOCOL_VERSION = "v1"

    def __init__(
        self,
        timeout_seconds: float = 60.0,
        max_tool_calls_per_run: int = 20,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_tool_calls_per_run = max_tool_calls_per_run
        self._agents: dict[str, tuple[Manifest, AgentRunner]] = {}

    def register_agent(self, manifest: Manifest, runner: AgentRunner) -> None:
        """Register an agent by its manifest. Overwrites if same name."""
        self._agents[manifest.name] = (manifest, runner)

    def unregister_agent(self, agent_id: str) -> bool:
        """Remove an agent. Returns True if it was registered."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            return True
        return False

    def get_agent_manifest(self, agent_id: str) -> Manifest | None:
        """Return the manifest for an agent, or None."""
        entry = self._agents.get(agent_id)
        return entry[0] if entry else None

    def list_agents(self) -> list[tuple[str, str]]:
        """Return list of (agent_id, version)."""
        return [(m.name, m.version) for m, _ in self._agents.values()]

    async def run(
        self,
        agent_id: str,
        input_data: dict[str, Any],
        *,
        correlation_id: str | None = None,
        timeout_seconds: float | None = None,
        max_tool_calls: int | None = None,
    ) -> RunResponse:
        """
        Dispatch a run request to the given agent. Raises if agent not found or timeout.
        """
        entry = self._agents.get(agent_id)
        if not entry:
            return _error_response(
                None,
                "agent_not_found",
                f"Agent not registered: {agent_id}",
            )
        manifest, runner = entry
        request_id = f"req-{uuid.uuid4().hex[:12]}"
        corr_id = correlation_id or f"corr-{uuid.uuid4().hex[:12]}"
        timeout = timeout_seconds if timeout_seconds is not None else self._timeout_seconds
        max_calls = max_tool_calls if max_tool_calls is not None else self._max_tool_calls_per_run

        run_request: RunRequest = {
            "type": "run_request",
            "id": request_id,
            "protocol": self.PROTOCOL_VERSION,
            "agent_id": agent_id,
            "agent_version": manifest.version,
            "input": input_data,
            "options": {
                "timeout_seconds": timeout,
                "max_tool_calls": max_calls,
                "correlation_id": corr_id,
            },
        }

        start = time.monotonic()
        try:
            if asyncio.iscoroutinefunction(runner):
                response = await asyncio.wait_for(
                    runner(run_request),
                    timeout=timeout,
                )
            else:
                loop = asyncio.get_event_loop()
                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: runner(run_request),
                    ),
                    timeout=timeout,
                )
            if asyncio.iscoroutine(response):
                response = await asyncio.wait_for(response, timeout=timeout)
        except asyncio.TimeoutError:
            try:
                from agentfabric.observability import record_run
                record_run(agent_id, False, time.monotonic() - start)
            except ImportError:
                pass
            return _error_response(
                request_id,
                "timeout",
                f"Run exceeded timeout of {timeout}s",
            )
        except Exception as e:
            try:
                from agentfabric.observability import record_run
                record_run(agent_id, False, time.monotonic() - start)
            except ImportError:
                pass
            return _error_response(
                request_id,
                "run_error",
                str(e),
            )

        try:
            from agentfabric.observability import record_run
            record_run(agent_id, response.get("success", False), time.monotonic() - start)
        except ImportError:
            pass
        if not response.get("request_id"):
            response["request_id"] = request_id
        return response

    def run_sync(
        self,
        agent_id: str,
        input_data: dict[str, Any],
        **kwargs: Any,
    ) -> RunResponse:
        """Synchronous wrapper for run()."""
        return asyncio.run(self.run(agent_id, input_data, **kwargs))


def _error_response(
    request_id: str | None,
    code: str,
    message: str,
) -> RunResponse:
    return {
        "type": "run_response",
        "id": f"resp-{uuid.uuid4().hex[:12]}",
        "request_id": request_id or "",
        "success": False,
        "output": None,
        "error": {"code": code, "message": message},
        "events": [],
    }
