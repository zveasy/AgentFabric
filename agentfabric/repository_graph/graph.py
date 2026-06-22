"""Repository lineage, dependency, and impact graph."""

from __future__ import annotations

from dataclasses import dataclass

from agentfabric.repository_lifecycle import RepositoryRecord


@dataclass(frozen=True)
class ImpactAnalysis:
    repository_id: str
    direct_dependents: tuple[str, ...]
    transitive_dependents: tuple[str, ...]
    drifted_dependencies: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "repository_id": self.repository_id,
            "direct_dependents": list(self.direct_dependents),
            "transitive_dependents": list(self.transitive_dependents),
            "drifted_dependencies": list(self.drifted_dependencies),
        }


class RepositoryGraph:
    def __init__(self, repositories: list[RepositoryRecord]) -> None:
        self.repositories = {item.repository_id: item for item in repositories}

    def lineage(self) -> list[dict[str, object]]:
        return [
            {
                "repository_id": item.repository_id,
                "parent_repository_id": item.parent_repository_id,
                "lineage_action": item.lineage_action,
                "version": item.version,
            }
            for item in sorted(self.repositories.values(), key=lambda record: record.repository_id)
        ]

    def dependencies(self) -> dict[str, list[str]]:
        return {
            item.repository_id: sorted(item.dependencies)
            for item in sorted(self.repositories.values(), key=lambda record: record.repository_id)
        }

    def impact(self, repository_id: str) -> ImpactAnalysis:
        direct = sorted(
            item.repository_id for item in self.repositories.values() if repository_id in item.dependencies
        )
        transitive = set(direct)
        queue = list(direct)
        while queue:
            current = queue.pop(0)
            for item in self.repositories.values():
                if current in item.dependencies and item.repository_id not in transitive:
                    transitive.add(item.repository_id)
                    queue.append(item.repository_id)
        if repository_id not in self.repositories:
            raise KeyError("repository not found")
        drifted = sorted(
            dependency for dependency in self.repositories[repository_id].dependencies
            if dependency not in self.repositories
        )
        return ImpactAnalysis(repository_id, tuple(direct), tuple(sorted(transitive)), tuple(drifted))
