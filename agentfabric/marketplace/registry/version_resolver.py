"""Marketplace version resolution."""

from __future__ import annotations

from agentfabric.marketplace.packages import PackageVersion


class VersionResolver:
    def latest(self, versions: list[PackageVersion]) -> PackageVersion:
        if not versions:
            raise KeyError("no package versions available")
        return sorted(versions, key=lambda item: item.version)[-1]

    def compatible(self, versions: list[PackageVersion], constraint: str | None = None) -> PackageVersion:
        if not constraint:
            return self.latest(versions)
        matched = [item for item in versions if _compatible(item.version, constraint)]
        return self.latest(matched)


def _compatible(version: str, constraint: str) -> bool:
    if constraint in {"*", version}:
        return True
    if constraint.endswith(".x"):
        return version.split(".")[0] == constraint.split(".")[0]
    if constraint.startswith(">="):
        return version >= constraint[2:]
    return False
