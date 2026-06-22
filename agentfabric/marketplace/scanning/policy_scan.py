"""Manifest policy scanner."""

from __future__ import annotations

from agentfabric.marketplace.packages import PackageVersion
from agentfabric.marketplace.packages.package_manifest import INDUSTRY_PACKAGE_CATEGORIES


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
        if package.metadata.category not in INDUSTRY_PACKAGE_CATEGORIES:
            findings.append("unsupported industry package category")
        if package.metadata.quality_score is not None and package.metadata.quality_score < 0.8:
            findings.append("industry package quality score is below threshold")
        return {"findings": findings, "ok": not findings}
