"""Policy-driven agent delegation/handoff orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Callable, Any

from agentfabric.errors import AuthorizationError, ValidationError
from agentfabric.phase3.protocol import CollaborationMessage


@dataclass
class CollaborationPolicy:
    allowed_edges: set[tuple[str, str]] = field(default_factory=set)
    max_delegations_per_run: int = 10
    max_timeout_seconds: float = 300.0


class CollaborationOrchestrator:
    """Executes delegation with policy and quota enforcement."""

    def __init__(self, policy: CollaborationPolicy) -> None:
        self._policy = policy
        self._delegation_counts_by_correlation_id: dict[str, int] = {}

    def allow_edge(self, source: str, target: str) -> None:
        self._policy.allowed_edges.add((source, target))

    def delegate(
        self,
        message: CollaborationMessage,
        delegate_handler: Callable[[CollaborationMessage], dict[str, Any]],
    ) -> dict[str, Any]:
        edge = (message.source_agent, message.target_agent)
        if edge not in self._policy.allowed_edges:
            raise AuthorizationError("agent delegation edge is not allowed")
        if message.timeout_seconds > self._policy.max_timeout_seconds:
            raise ValidationError("delegation timeout exceeds policy limit")

        correlation_id = message.trace.correlation_id
        count = self._delegation_counts_by_correlation_id.get(correlation_id, 0) + 1
        if count > self._policy.max_delegations_per_run:
            raise AuthorizationError("delegation quota exceeded")
        self._delegation_counts_by_correlation_id[correlation_id] = count

        start = monotonic()
        result = delegate_handler(message)
        duration_seconds = monotonic() - start
        return {
            "correlation_id": correlation_id,
            "source_agent": message.source_agent,
            "target_agent": message.target_agent,
            "duration_seconds": round(duration_seconds, 6),
            "result": result,
        }
