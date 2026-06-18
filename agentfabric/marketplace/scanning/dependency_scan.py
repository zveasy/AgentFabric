"""Dependency scanner."""

from __future__ import annotations

from agentfabric.marketplace.packages import PackageVersion


class DependencyScanner:
    def scan(self, package: PackageVersion, available: dict[str, PackageVersion]) -> dict[str, object]:
        missing = [
            dependency.package_id
            for dependency in package.manifest.dependencies
            if dependency.required and dependency.package_id not in available
        ]
        deprecated = [dependency.package_id for dependency in package.manifest.dependencies if dependency.deprecated]
        unsigned = [
            dependency.package_id
            for dependency in package.manifest.dependencies
            if dependency.package_id in available and not available[dependency.package_id].signature
        ]
        return {"missing": missing, "deprecated": deprecated, "unsigned": unsigned, "ok": not (missing or deprecated or unsigned)}
