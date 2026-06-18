"""Dependency utilities for task graphs."""

from __future__ import annotations

from collections import defaultdict, deque

from agentfabric.errors import ValidationError

from .task_graph import TaskGraph, TaskNode


class DependencyGraph:
    def __init__(self, task_graph: TaskGraph) -> None:
        self.task_graph = task_graph
        self.by_id = {node.node_id: node for node in task_graph.nodes}
        if len(self.by_id) != len(task_graph.nodes):
            raise ValidationError("task graph contains duplicate node_id values")
        self.children: defaultdict[str, list[str]] = defaultdict(list)
        self.indegree = {node.node_id: 0 for node in task_graph.nodes}
        for node in task_graph.nodes:
            for dep in node.dependencies:
                if dep not in self.by_id:
                    raise ValidationError(f"unknown dependency: {dep}")
                self.children[dep].append(node.node_id)
                self.indegree[node.node_id] += 1

    def topological_batches(self) -> list[list[TaskNode]]:
        indegree = dict(self.indegree)
        queue = deque([node_id for node_id, degree in indegree.items() if degree == 0])
        batches: list[list[TaskNode]] = []
        visited = 0
        while queue:
            current_ids = list(queue)
            queue.clear()
            batches.append([self.by_id[node_id] for node_id in current_ids])
            for node_id in current_ids:
                visited += 1
                for child in self.children[node_id]:
                    indegree[child] -= 1
                    if indegree[child] == 0:
                        queue.append(child)
        if visited != len(self.by_id):
            raise ValidationError("task graph contains cycles")
        return batches
