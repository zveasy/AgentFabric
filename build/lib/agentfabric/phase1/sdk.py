"""SDK primitives for building phase-1 compatible agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from agentfabric.errors import ConflictError
from agentfabric.phase1.memory import MemoryScope, ScopedMemoryStore
from agentfabric.phase1.protocol import ProtocolEnvelope
from agentfabric.phase1.sandbox import Sandbox
from agentfabric.phase1.tools import ToolRouter


class AgentExecutionContext:
    """Execution context passed to Agent.run()."""

    def __init__(
        self,
        *,
        correlation_id: str,
        agent_id: str,
        user_id: str,
        session_id: str,
        tool_router: ToolRouter,
        manifest,
        memory_store: ScopedMemoryStore,
        sandbox: Sandbox,
        max_tool_calls: int,
        cancellation_check: Callable[[], bool],
    ) -> None:
        self.correlation_id = correlation_id
        self.agent_id = agent_id
        self._tool_router = tool_router
        self._manifest = manifest
        self._memory_store = memory_store
        self._scope = MemoryScope(user_id=user_id, session_id=session_id, agent_id=agent_id)
        self.sandbox = sandbox
        self._max_tool_calls = max_tool_calls
        self._tool_calls = 0
        self._events: list[dict[str, Any]] = []
        self._cancellation_check = cancellation_check

    def _assert_not_cancelled(self) -> None:
        if self._cancellation_check():
            raise ConflictError("run cancelled")

    def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        self._assert_not_cancelled()
        self._tool_calls += 1
        if self._tool_calls > self._max_tool_calls:
            raise ConflictError("tool call limit exceeded")
        envelope: ProtocolEnvelope = self._tool_router.invoke(
            self._manifest,
            name,
            args,
            correlation_id=self.correlation_id,
        )
        return envelope.payload["result"]

    def memory_set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        self._assert_not_cancelled()
        self._memory_store.set(self._scope, key, value, ttl_seconds)

    def memory_get(self, key: str) -> Any | None:
        self._assert_not_cancelled()
        return self._memory_store.get(self._scope, key)

    def emit_event(self, event_name: str, **payload: Any) -> None:
        self._events.append({"event_name": event_name, "payload": payload})

    def events(self) -> list[dict[str, Any]]:
        return list(self._events)


class Agent(ABC):
    """Base class for SDK agents."""

    @abstractmethod
    def run(self, request: dict[str, Any], ctx: AgentExecutionContext) -> dict[str, Any]:
        raise NotImplementedError
