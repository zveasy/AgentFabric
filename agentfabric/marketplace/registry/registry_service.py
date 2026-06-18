"""Durable marketplace package registry."""

from __future__ import annotations

from agentfabric.errors import NotFoundError
from agentfabric.marketplace.packages import PackageVersion
from agentfabric.persistence import PersistenceStore

from .version_resolver import VersionResolver


class MarketplaceRegistryService:
    def __init__(self, persistence: PersistenceStore) -> None:
        self.persistence = persistence
        self.persistence.initialize()

    def save_version(self, package: PackageVersion) -> None:
        self.persistence.put("marketplace_packages", package.key, package.as_dict())

    def list_packages(self, tenant_id: str | None = None) -> list[PackageVersion]:
        rows = self.persistence.list("marketplace_packages")
        versions = [PackageVersion.from_dict(row) for row in rows]
        if tenant_id is None:
            return versions
        return [
            item for item in versions
            if item.manifest.publisher_tenant_id == tenant_id or not item.metadata.private
        ]

    def get(self, package_id: str, version: str | None = None) -> PackageVersion:
        versions = [item for item in self.list_packages() if item.package_id == package_id]
        if not versions:
            raise NotFoundError("package not found")
        if version:
            for item in versions:
                if item.version == version:
                    return item
            raise NotFoundError("package version not found")
        return VersionResolver().latest(versions)

    def available_by_id(self) -> dict[str, PackageVersion]:
        latest: dict[str, PackageVersion] = {}
        for package in self.list_packages():
            existing = latest.get(package.package_id)
            if existing is None or package.version > existing.version:
                latest[package.package_id] = package
        return latest
