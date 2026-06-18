"""Dependency graph for marketplace packages."""

from __future__ import annotations

from collections import defaultdict

from agentfabric.marketplace.packages import PackageVersion


class DependencyGraph:
    def __init__(self, packages: list[PackageVersion]) -> None:
        self.packages = {package.package_id: package for package in packages}
        self.edges: defaultdict[str, list[str]] = defaultdict(list)
        for package in packages:
            for dependency in package.manifest.dependencies:
                self.edges[package.package_id].append(dependency.package_id)

    def detect_cycles(self) -> list[list[str]]:
        cycles: list[list[str]] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str, path: list[str]) -> None:
            if node in visiting:
                cycles.append(path[path.index(node):] + [node])
                return
            if node in visited:
                return
            visiting.add(node)
            for child in self.edges.get(node, []):
                visit(child, path + [child])
            visiting.remove(node)
            visited.add(node)

        for package_id in self.packages:
            visit(package_id, [package_id])
        return cycles
