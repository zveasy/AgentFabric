"""Workflow execution engine for distributed task graphs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Callable

from agentfabric.errors import ConflictError
from agentfabric.events import EventStore, EventType
from agentfabric.reputation import ReputationService

from .context_store import ContextStore
from .dependency_graph import DependencyGraph
from .task_graph import TaskGraph, TaskNode


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class WorkflowState:
    workflow_id: str
    status: str = "pending"
    node_results: dict[str, object] = field(default_factory=dict)
    node_status: dict[str, str] = field(default_factory=dict)
    retry_counters: dict[str, int] = field(default_factory=dict)
    delegated_assignments: dict[str, str] = field(default_factory=dict)
    checkpoints: list[str] = field(default_factory=list)
    traces: list[dict[str, object]] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "workflow_id": self.workflow_id,
            "status": self.status,
            "node_results": dict(self.node_results),
            "node_status": dict(self.node_status),
            "retry_counters": dict(self.retry_counters),
            "completed_task_ids": [node_id for node_id, status in self.node_status.items() if status == "completed"],
            "pending_task_ids": [node_id for node_id, status in self.node_status.items() if status == "pending"],
            "failed_task_ids": [node_id for node_id, status in self.node_status.items() if status == "failed"],
            "delegated_assignments": dict(self.delegated_assignments),
            "checkpoints": list(self.checkpoints),
            "traces": list(self.traces),
        }


NodeRunner = Callable[[TaskNode, dict[str, object]], object]


class MeshWorkflowEngine:
    def __init__(
        self,
        *,
        context_store: ContextStore | None = None,
        event_store: EventStore | None = None,
        reputation: ReputationService | None = None,
    ) -> None:
        self.context_store = context_store or ContextStore()
        self.event_store = event_store or EventStore()
        self.reputation = reputation or ReputationService()
        self._states: dict[str, WorkflowState] = {}

    def start(
        self,
        *,
        task_graph: TaskGraph,
        initial_payload: dict[str, object],
        node_runner: NodeRunner,
        approved_nodes: set[str] | None = None,
        parallel: bool = True,
    ) -> dict[str, object]:
        approved_nodes = approved_nodes or set()
        graph = DependencyGraph(task_graph)
        state = WorkflowState(workflow_id=task_graph.graph_id, status="running")
        tenant_id = str(initial_payload.get("tenant_id", "")) if initial_payload.get("tenant_id") else None
        organization_id = str(initial_payload.get("organization_id", "")) if initial_payload.get("organization_id") else None
        for node in task_graph.nodes:
            state.node_status[node.node_id] = "pending"
            state.delegated_assignments[node.node_id] = node.agent_id
        self._states[task_graph.graph_id] = state
        self.context_store.get_or_create(task_graph.graph_id).conversation_state.update(initial_payload)
        self.event_store.append(
            "workflow.started",
            task_graph.graph_id,
            {
                "status": "started",
                "tenant_id": tenant_id,
                "organization_id": organization_id,
                "task_graph": {
                    "graph_id": task_graph.graph_id,
                    "nodes": [
                        {
                            "node_id": node.node_id,
                            "agent_id": node.agent_id,
                            "capability": node.capability,
                            "dependencies": list(node.dependencies),
                            "max_retries": node.max_retries,
                            "requires_human_approval": node.requires_human_approval,
                            "payload": dict(node.payload),
                        }
                        for node in task_graph.nodes
                    ],
                },
                "initial_payload": dict(initial_payload),
            },
        )

        for batch in graph.topological_batches():
            pending_approval = [
                node for node in batch if node.requires_human_approval and node.node_id not in approved_nodes
            ]
            if pending_approval:
                for node in pending_approval:
                    state.node_status[node.node_id] = "awaiting_approval"
                state.status = "awaiting_approval"
                self.event_store.append(
                    "human_approval.requested",
                    task_graph.graph_id,
                    {
                        "status": "awaiting_approval",
                        "tenant_id": tenant_id,
                        "organization_id": organization_id,
                        "nodes": [node.node_id for node in pending_approval],
                    },
                )
                return state.as_dict()

            if parallel and len(batch) > 1:
                with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                    futures = {
                        pool.submit(self._run_node_with_retries, state, task_graph.graph_id, node, initial_payload, node_runner): node
                        for node in batch
                    }
                    for future in as_completed(futures):
                        future.result()
            else:
                for node in batch:
                    self._run_node_with_retries(state, task_graph.graph_id, node, initial_payload, node_runner)
            checkpoint_id = f"batch-{len(state.checkpoints) + 1}"
            snapshot = self.context_store.checkpoint(task_graph.graph_id, checkpoint_id)
            state.checkpoints.append(checkpoint_id)
            self.event_store.append(
                "checkpoint.created",
                task_graph.graph_id,
                {
                    "checkpoint_id": checkpoint_id,
                    "tenant_id": tenant_id,
                    "organization_id": organization_id,
                    "workflow_state": state.as_dict(),
                    "shared_context": snapshot,
                },
            )

        state.status = "completed"
        self.event_store.append(
            EventType.WORKFLOW.value,
            task_graph.graph_id,
            {"status": "completed", "tenant_id": tenant_id, "organization_id": organization_id},
        )
        self.event_store.append(
            "workflow.completed",
            task_graph.graph_id,
            {**state.as_dict(), "tenant_id": tenant_id, "organization_id": organization_id},
        )
        return state.as_dict()

    def get(self, workflow_id: str) -> dict[str, object] | None:
        state = self._states.get(workflow_id)
        return state.as_dict() if state else None

    def recover_from_checkpoint(self, workflow_id: str, checkpoint_id: str) -> dict[str, object]:
        return self.context_store.restore(workflow_id, checkpoint_id)

    def _run_node_with_retries(
        self,
        state: WorkflowState,
        workflow_id: str,
        node: TaskNode,
        initial_payload: dict[str, object],
        node_runner: NodeRunner,
    ) -> None:
        attempts = 0
        tenant_id = str(initial_payload.get("tenant_id", "")) if initial_payload.get("tenant_id") else None
        organization_id = str(initial_payload.get("organization_id", "")) if initial_payload.get("organization_id") else None
        while attempts <= node.max_retries:
            attempts += 1
            state.retry_counters[node.node_id] = attempts
            started = perf_counter()
            started_at = utc_now()
            try:
                self.event_store.append(
                    "task.started",
                    workflow_id,
                    {
                        "node_id": node.node_id,
                        "agent_id": node.agent_id,
                        "attempt": attempts,
                        "tenant_id": tenant_id,
                        "organization_id": organization_id,
                    },
                )
                payload = {
                    "workflow_id": workflow_id,
                    "node_id": node.node_id,
                    "initial_payload": dict(initial_payload),
                    "node_payload": dict(node.payload),
                    "dependency_results": {
                        dep: state.node_results[dep] for dep in node.dependencies if dep in state.node_results
                    },
                    "shared_context": self.context_store.get_or_create(workflow_id).snapshot(),
                }
                result = node_runner(node, payload)
                latency_ms = (perf_counter() - started) * 1000
                state.node_results[node.node_id] = result
                state.node_status[node.node_id] = "completed"
                trace = {
                    "node_id": node.node_id,
                    "agent_id": node.agent_id,
                    "attempt": attempts,
                    "status": "completed",
                    "started_at": started_at.isoformat(),
                    "finished_at": utc_now().isoformat(),
                    "latency_ms": latency_ms,
                    "tenant_id": tenant_id,
                    "organization_id": organization_id,
                }
                state.traces.append(trace)
                self.context_store.update_task_state(workflow_id, node.node_id, {"status": "completed", "result": result})
                self.event_store.append(EventType.TASK.value, workflow_id, trace)
                self.event_store.append("task.completed", workflow_id, {**trace, "result": result})
                self.reputation.record_task(node.agent_id, success=True, latency_ms=latency_ms, tenant_id=tenant_id)
                return
            except Exception as exc:
                latency_ms = (perf_counter() - started) * 1000
                trace = {
                    "node_id": node.node_id,
                    "agent_id": node.agent_id,
                    "attempt": attempts,
                    "status": "failed",
                    "error": str(exc),
                    "started_at": started_at.isoformat(),
                    "finished_at": utc_now().isoformat(),
                    "latency_ms": latency_ms,
                    "tenant_id": tenant_id,
                    "organization_id": organization_id,
                }
                state.traces.append(trace)
                self.event_store.append(EventType.TASK.value, workflow_id, trace)
                self.event_store.append("task.failed", workflow_id, trace)
                self.reputation.record_task(node.agent_id, success=False, latency_ms=latency_ms, tenant_id=tenant_id)
                if attempts > node.max_retries:
                    state.node_status[node.node_id] = "failed"
                    state.status = "failed"
                    raise ConflictError(f"workflow failed at {node.node_id}: {exc}") from exc
