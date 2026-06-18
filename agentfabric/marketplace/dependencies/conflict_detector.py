"""Dependency conflict detection."""

from __future__ import annotations

from agentfabric.errors import ValidationError
from agentfabric.marketplace.packages import PackageVersion


class ConflictDetector:
    def validate(self, package: PackageVersion, available: dict[str, PackageVersion]) -> None:
        for dependency in package.manifest.dependencies:
            if dependency.required and dependency.package_id not in available:
                raise ValidationError(f"missing dependency: {dependency.package_id}")
            if dependency.deprecated:
                raise ValidationError(f"deprecated dependency: {dependency.package_id}")
            resolved = available.get(dependency.package_id)
            if resolved and not _compatible(resolved.version, dependency.version_constraint):
                raise ValidationError(f"incompatible dependency: {dependency.package_id}")


def _compatible(version: str, constraint: str) -> bool:
    if constraint in {"*", version}:
        return True
    if constraint.endswith(".x"):
        return version.split(".")[0] == constraint.split(".")[0]
    if constraint.startswith(">="):
        return version >= constraint[2:]
    return False
