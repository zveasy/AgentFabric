"""Dependency resolver."""

from __future__ import annotations

from agentfabric.errors import ValidationError
from agentfabric.marketplace.packages import PackageVersion

from .conflict_detector import ConflictDetector
from .dependency_graph import DependencyGraph


class DependencyResolver:
    def resolve(self, package: PackageVersion, available: dict[str, PackageVersion]) -> list[PackageVersion]:
        ConflictDetector().validate(package, available)
        resolved = [package]
        for dependency in package.manifest.dependencies:
            if dependency.package_id in available:
                resolved.append(available[dependency.package_id])
        graph = DependencyGraph(resolved)
        cycles = graph.detect_cycles()
        if cycles:
            raise ValidationError("circular dependency detected")
        unsafe_permissions = {
            permission
            for item in resolved[1:]
            for permission in item.manifest.tool_permissions
            if permission in {"tenant.data.all", "network.unbounded", "veil.restore"}
        }
        if unsafe_permissions:
            raise ValidationError(f"unsafe transitive permissions: {', '.join(sorted(unsafe_permissions))}")
        return resolved
