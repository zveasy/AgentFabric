"""Task graph declarations for multi-agent collaboration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TaskNode:
    node_id: str
    agent_id: str
    capability: str | None = None
    dependencies: tuple[str, ...] = ()
    max_retries: int = 0
    requires_human_approval: bool = False
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskGraph:
    graph_id: str
    nodes: tuple[TaskNode, ...]

    @classmethod
    def from_dicts(cls, graph_id: str, nodes: list[dict[str, object]]) -> "TaskGraph":
        return cls(
            graph_id=graph_id,
            nodes=tuple(
                TaskNode(
                    node_id=str(item["node_id"]),
                    agent_id=str(item.get("agent_id") or item.get("agent_name") or item["node_id"]),
                    capability=str(item["capability"]) if item.get("capability") else None,
                    dependencies=tuple(str(dep) for dep in item.get("dependencies", ())),
                    max_retries=int(item.get("max_retries", 0)),
                    requires_human_approval=bool(item.get("requires_human_approval", False)),
                    payload=dict(item.get("payload", {})),
                )
                for item in nodes
            ),
        )
