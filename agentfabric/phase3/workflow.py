"""DAG workflow runtime for multi-agent orchestration."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from agentfabric.errors import ConflictError, ValidationError


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class WorkflowNode:
    node_id: str
    agent_name: str
    dependencies: tuple[str, ...] = ()
    max_retries: int = 0
    timeout_seconds: float = 30.0


@dataclass
class NodeState:
    attempts: int = 0
    status: str = "pending"
    result: Any = None
    error: str | None = None


class WorkflowEngine:
    """Executes DAG nodes with retries and run-level idempotency."""

    def __init__(self) -> None:
        self._run_cache: dict[str, dict[str, Any]] = {}

    def run(
        self,
        *,
        workflow_id: str,
        idempotency_key: str,
        nodes: list[WorkflowNode],
        initial_payload: dict[str, Any],
        node_runner: Callable[[WorkflowNode, dict[str, Any]], Any],
    ) -> dict[str, Any]:
        cache_key = f"{workflow_id}:{idempotency_key}"
        if cache_key in self._run_cache:
            return self._run_cache[cache_key]

        ordered_nodes = self._topological_sort(nodes)
        state: dict[str, NodeState] = {node.node_id: NodeState() for node in ordered_nodes}
        traces: list[dict[str, Any]] = []
        context: dict[str, Any] = dict(initial_payload)

        for node in ordered_nodes:
            node_state = state[node.node_id]
            last_error: str | None = None
            while node_state.attempts <= node.max_retries:
                node_state.attempts += 1
                started_at = utc_now()
                try:
                    node_input = {
                        "workflow_id": workflow_id,
                        "node_id": node.node_id,
                        "context": dict(context),
                        "dependency_results": {
                            dep: state[dep].result for dep in node.dependencies
                        },
                    }
                    result = node_runner(node, node_input)
                    node_state.result = result
                    node_state.status = "completed"
                    context[node.node_id] = result
                    traces.append(
                        {
                            "node_id": node.node_id,
                            "agent_name": node.agent_name,
                            "attempt": node_state.attempts,
                            "status": "completed",
                            "started_at": started_at.isoformat(),
                            "finished_at": utc_now().isoformat(),
                        }
                    )
                    break
                except Exception as exc:  # pragma: no cover - runtime safety branch
                    last_error = str(exc)
                    traces.append(
                        {
                            "node_id": node.node_id,
                            "agent_name": node.agent_name,
                            "attempt": node_state.attempts,
                            "status": "failed",
                            "error": last_error,
                            "started_at": started_at.isoformat(),
                            "finished_at": utc_now().isoformat(),
                        }
                    )
                    if node_state.attempts > node.max_retries:
                        node_state.status = "failed"
                        node_state.error = last_error
                        raise ConflictError(f"workflow failed at {node.node_id}: {last_error}") from exc

        output = {
            "workflow_id": workflow_id,
            "idempotency_key": idempotency_key,
            "status": "completed",
            "node_results": {node_id: item.result for node_id, item in state.items()},
            "traces": traces,
        }
        self._run_cache[cache_key] = output
        return output

    def _topological_sort(self, nodes: list[WorkflowNode]) -> list[WorkflowNode]:
        by_id = {node.node_id: node for node in nodes}
        if len(by_id) != len(nodes):
            raise ValidationError("workflow has duplicate node_id values")

        indegree = {node.node_id: 0 for node in nodes}
        graph: defaultdict[str, list[str]] = defaultdict(list)
        for node in nodes:
            for dep in node.dependencies:
                if dep not in by_id:
                    raise ValidationError(f"unknown dependency: {dep}")
                graph[dep].append(node.node_id)
                indegree[node.node_id] += 1

        queue = deque([node_id for node_id, degree in indegree.items() if degree == 0])
        ordered_ids: list[str] = []
        while queue:
            node_id = queue.popleft()
            ordered_ids.append(node_id)
            for child in graph[node_id]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)

        if len(ordered_ids) != len(nodes):
            raise ValidationError("workflow graph contains cycles")
        return [by_id[node_id] for node_id in ordered_ids]
