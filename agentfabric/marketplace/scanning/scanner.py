"""Composite package scanner."""

from __future__ import annotations

from agentfabric.errors import ValidationError
from agentfabric.marketplace.packages import PackageVersion

from .dependency_scan import DependencyScanner
from .permission_scan import PermissionScanner
from .policy_scan import PolicyScanner


class MarketplaceScanner:
    def scan(self, package: PackageVersion, available: dict[str, PackageVersion] | None = None) -> dict[str, object]:
        available = available or {}
        permission = PermissionScanner().scan(package)
        dependency = DependencyScanner().scan(package, available)
        policy = PolicyScanner().scan(package)
        ok = bool(dependency["ok"] and policy["ok"] and not permission["requires_approval"])
        return {"ok": ok, "permission": permission, "dependency": dependency, "policy": policy}

    def enforce(self, package: PackageVersion, available: dict[str, PackageVersion] | None = None) -> dict[str, object]:
        result = self.scan(package, available)
        if not result["ok"] and not package.metadata.high_risk_approved:
            raise ValidationError("package failed marketplace scan")
        return result
