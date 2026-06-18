"""Marketplace install, upgrade, rollback and entitlement operations."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agentfabric.errors import AuthorizationError, ValidationError
from agentfabric.events import EventStore
from agentfabric.marketplace.dependencies import DependencyResolver
from agentfabric.marketplace.licensing import Entitlement, LicenseChecker
from agentfabric.marketplace.packages import PackageVersion
from agentfabric.marketplace.scanning import MarketplaceScanner
from agentfabric.persistence import PersistenceStore

from .registry_service import MarketplaceRegistryService


class InstallService:
    def __init__(self, *, registry: MarketplaceRegistryService, persistence: PersistenceStore, event_store: EventStore) -> None:
        self.registry = registry
        self.persistence = persistence
        self.event_store = event_store

    def install(self, *, tenant_id: str, package_id: str, version: str | None = None, approved_permissions: bool = False) -> dict[str, object]:
        package = self.registry.get(package_id, version)
        self._validate_install(tenant_id, package, approved_permissions=approved_permissions)
        entitlement = Entitlement(
            tenant_id=tenant_id,
            package_id=package.package_id,
            version=package.version,
            license_type=package.manifest.license_type,
        )
        install = {
            "install_id": f"inst-{uuid4().hex[:12]}",
            "tenant_id": tenant_id,
            "package_id": package.package_id,
            "publisher_tenant_id": package.manifest.publisher_tenant_id,
            "version": package.version,
            "installed_at": datetime.now(tz=timezone.utc).isoformat(),
            "active": True,
        }
        self.persistence.put("marketplace_entitlements", entitlement.entitlement_id, entitlement.as_dict())
        self.persistence.put("marketplace_installs", install["install_id"], install)
        self.event_store.append("marketplace.entitlement.granted", package.package_id, {"tenant_id": tenant_id, **entitlement.as_dict()})
        self.event_store.append("marketplace.package.installed", package.package_id, install)
        return install

    def uninstall(self, *, tenant_id: str, package_id: str) -> dict[str, object]:
        install = self._active_install(tenant_id, package_id)
        install["active"] = False
        self.persistence.put("marketplace_installs", str(install["install_id"]), install)
        self.event_store.append("marketplace.package.uninstalled", package_id, {"tenant_id": tenant_id, "package_id": package_id})
        return install

    def upgrade(self, *, tenant_id: str, package_id: str, version: str | None = None) -> dict[str, object]:
        package = self.registry.get(package_id, version)
        self._validate_install(tenant_id, package, approved_permissions=True)
        current = self._active_install(tenant_id, package_id)
        current["version"] = package.version
        current["upgraded_at"] = datetime.now(tz=timezone.utc).isoformat()
        self.persistence.put("marketplace_installs", str(current["install_id"]), current)
        self.event_store.append("marketplace.package.upgraded", package_id, {"tenant_id": tenant_id, "package_id": package_id, "version": package.version})
        return current

    def rollback(self, *, tenant_id: str, package_id: str, version: str, admin_override: bool = False) -> dict[str, object]:
        package = self.registry.get(package_id, version)
        if package.metadata.revoked and not admin_override:
            raise ValidationError("cannot rollback to revoked package version")
        current = self._active_install(tenant_id, package_id)
        current["version"] = package.version
        current["rolled_back_at"] = datetime.now(tz=timezone.utc).isoformat()
        self.persistence.put("marketplace_installs", str(current["install_id"]), current)
        self.event_store.append("marketplace.package.rolled_back", package_id, {"tenant_id": tenant_id, "package_id": package_id, "version": package.version})
        return current

    def verify_runtime_entitlement(self, *, tenant_id: str, package_id: str) -> None:
        entitlement = None
        for item in self.persistence.list_tenant("marketplace_entitlements", tenant_id):
            if item["package_id"] == package_id and item.get("active", True):
                entitlement = Entitlement.from_dict(item)
                break
        LicenseChecker().verify(entitlement)

    def list_installed(self, tenant_id: str) -> list[dict[str, object]]:
        return self.persistence.list_tenant("marketplace_installs", tenant_id)

    def _validate_install(self, tenant_id: str, package: PackageVersion, *, approved_permissions: bool) -> None:
        if package.metadata.private and package.manifest.publisher_tenant_id != tenant_id:
            raise AuthorizationError("tenant cannot install private package")
        scan = MarketplaceScanner().scan(package, self.registry.available_by_id())
        if scan["permission"]["requires_approval"] and not (approved_permissions or package.metadata.high_risk_approved):
            raise AuthorizationError("high-risk package permissions require approval")
        if not scan["dependency"]["ok"] or not scan["policy"]["ok"]:
            raise ValidationError("package failed install scan")
        DependencyResolver().resolve(package, self.registry.available_by_id())

    def _active_install(self, tenant_id: str, package_id: str) -> dict[str, object]:
        for install in self.persistence.list_tenant("marketplace_installs", tenant_id):
            if install["package_id"] == package_id and install.get("active", True):
                return install
        raise ValidationError("package is not installed")
