"""Repository dependency graph validation."""

from __future__ import annotations


class RepositoryDependencyGraph:
    def __init__(self) -> None:
        self._edges: dict[str, set[str]] = {}

    def add(self, repository_id: str, dependencies: tuple[str, ...]) -> None:
        self._edges[repository_id] = set(dependencies)
        self.validate()

    def validate(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError("circular repository dependency detected")
            if node in visited:
                return
            visiting.add(node)
            for dependency in self._edges.get(node, set()):
                if dependency in self._edges:
                    visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in sorted(self._edges):
            visit(node)

    def dependencies(self, repository_id: str) -> tuple[str, ...]:
        return tuple(sorted(self._edges.get(repository_id, set())))

    def as_dict(self) -> dict[str, object]:
        return {key: sorted(value) for key, value in sorted(self._edges.items())}
