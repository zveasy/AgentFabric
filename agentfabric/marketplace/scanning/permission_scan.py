"""Permission risk scanner."""

from __future__ import annotations

from agentfabric.marketplace.packages import PackageVersion

HIGH_RISK_PERMISSIONS = {
    "network.unbounded",
    "tenant.data.all",
    "memory.unbounded",
    "events.write",
    "marketplace.admin",
    "veil.restore",
    "gmail.send",
    "calendar.write",
    "github.write",
    "jira.write",
    "slack.write",
    "servicenow.write",
    "s3.write",
    "custom_http.execute",
}


class PermissionScanner:
    def scan(self, package: PackageVersion) -> dict[str, object]:
        requested = set(package.manifest.tool_permissions) | set(package.manifest.connector_permissions)
        high_risk = sorted(requested & HIGH_RISK_PERMISSIONS)
        return {
            "requested_permissions": sorted(requested),
            "high_risk_permissions": high_risk,
            "requires_approval": bool(high_risk),
            "summary": "high-risk permissions require tenant approval" if high_risk else "no high-risk permissions",
        }
