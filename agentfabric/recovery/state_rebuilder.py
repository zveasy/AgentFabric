"""Rebuild workflow state from durable events."""

from __future__ import annotations

from agentfabric.events import AgentFabricEvent


class StateRebuilder:
    def rebuild_workflow(self, workflow_id: str, events: list[AgentFabricEvent]) -> dict[str, object]:
        state: dict[str, object] = {
            "workflow_id": workflow_id,
            "status": "unknown",
            "node_results": {},
            "node_status": {},
            "retry_counters": {},
            "completed_task_ids": [],
            "pending_task_ids": [],
            "failed_task_ids": [],
            "checkpoints": [],
            "delegated_assignments": {},
            "traces": [],
        }
        completed: set[str] = set()
        failed: set[str] = set()
        started: set[str] = set()

        for event in sorted(events, key=lambda item: item.sequence):
            payload = event.payload
            if event.event_type == "workflow.started":
                state["status"] = "running"
                graph = dict(payload.get("task_graph", {}))
                for node in graph.get("nodes", []):
                    node_id = str(node["node_id"])
                    state["node_status"][node_id] = "pending"
                    state["delegated_assignments"][node_id] = str(node["agent_id"])
            elif event.event_type == "task.started":
                node_id = str(payload["node_id"])
                started.add(node_id)
                state["retry_counters"][node_id] = int(payload.get("attempt", 1))
            elif event.event_type == "task.completed":
                node_id = str(payload["node_id"])
                completed.add(node_id)
                failed.discard(node_id)
                state["node_status"][node_id] = "completed"
                if "result" in payload:
                    state["node_results"][node_id] = payload["result"]
                state["traces"].append(dict(payload))
            elif event.event_type == "task.failed":
                node_id = str(payload["node_id"])
                if node_id not in completed:
                    failed.add(node_id)
                    state["node_status"][node_id] = "failed"
                state["retry_counters"][node_id] = int(payload.get("attempt", 1))
                state["traces"].append(dict(payload))
            elif event.event_type == "human_approval.requested":
                state["status"] = "awaiting_approval"
                for node_id in payload.get("nodes", []):
                    state["node_status"][str(node_id)] = "awaiting_approval"
            elif event.event_type == "human_approval.resolved":
                for node_id in payload.get("nodes", []):
                    state["node_status"][str(node_id)] = "pending"
                state["status"] = "running"
            elif event.event_type == "checkpoint.created":
                state["checkpoints"].append(str(payload["checkpoint_id"]))
            elif event.event_type == "workflow.completed":
                state["status"] = "completed"
            elif event.event_type == "workflow":
                if payload.get("status") == "completed":
                    state["status"] = "completed"

        state["completed_task_ids"] = sorted(completed)
        pending = set(state["node_status"]) - completed - failed
        state["pending_task_ids"] = sorted(pending)
        state["failed_task_ids"] = sorted(failed - completed)
        if state["status"] == "unknown" and started:
            state["status"] = "running"
        return state
