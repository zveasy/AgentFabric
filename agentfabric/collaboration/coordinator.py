"""Coordinator tying discovery, task graphs, and workflow execution together."""

from __future__ import annotations

from agentfabric.mesh import AgentDiscovery

from .task_graph import TaskGraph
from .workflow import MeshWorkflowEngine, NodeRunner


class CollaborationCoordinator:
    def __init__(self, *, discovery: AgentDiscovery, workflow_engine: MeshWorkflowEngine) -> None:
        self.discovery = discovery
        self.workflow_engine = workflow_engine

    def start_workflow(
        self,
        *,
        workflow_id: str,
        nodes: list[dict[str, object]],
        initial_payload: dict[str, object],
        node_runner: NodeRunner,
        approved_nodes: set[str] | None = None,
    ) -> dict[str, object]:
        resolved: list[dict[str, object]] = []
        for item in nodes:
            node = dict(item)
            if not node.get("agent_id") and node.get("capability"):
                matches = self.discovery.discover(capability=str(node["capability"]))
                if not matches:
                    raise ValueError(f"no healthy agent found for capability: {node['capability']}")
                node["agent_id"] = matches[0]["identity"]["agent_id"]
            resolved.append(node)
        return self.workflow_engine.start(
            task_graph=TaskGraph.from_dicts(workflow_id, resolved),
            initial_payload=initial_payload,
            node_runner=node_runner,
            approved_nodes=approved_nodes,
        )
