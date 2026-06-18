"""Marketplace package aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field

from .package_version import PackageVersion


@dataclass
class Package:
    package_id: str
    publisher_tenant_id: str
    versions: dict[str, PackageVersion] = field(default_factory=dict)

    def add_version(self, version: PackageVersion) -> None:
        self.versions[version.version] = version

    def latest(self) -> PackageVersion:
        if not self.versions:
            raise KeyError("package has no versions")
        return self.versions[sorted(self.versions)[-1]]
