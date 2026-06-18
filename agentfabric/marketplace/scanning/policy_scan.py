"""Manifest policy scanner."""

from __future__ import annotations

from agentfabric.marketplace.packages import PackageVersion


class PolicyScanner:
    def scan(self, package: PackageVersion) -> dict[str, object]:
        findings: list[str] = []
        manifest = package.manifest.as_dict()
        if any(str(key).lower().startswith("raw_") for key in manifest):
            findings.append("suspicious raw manifest field")
        if package.metadata.revoked:
            findings.append("package version is revoked")
        if package.metadata.deprecated:
            findings.append("package version is deprecated")
        return {"findings": findings, "ok": not findings}
