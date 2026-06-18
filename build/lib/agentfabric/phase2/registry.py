"""Registry storage, publish flow, discovery, install."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from math import ceil
from typing import Any

from agentfabric.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from agentfabric.phase2.models import AgentPackage, InstallRecord, PackageUpload
from agentfabric.phase2.pipeline import ManifestValidator, SignatureVerifier


class RegistryService:
    """In-memory package registry suitable for local/prototype use."""

    def __init__(self) -> None:
        self._packages: dict[tuple[str, str, str], AgentPackage] = {}
        self._latest_by_package: dict[tuple[str, str], AgentPackage] = {}
        self._installs: list[InstallRecord] = []
        self._installs_by_tenant: defaultdict[str, list[InstallRecord]] = defaultdict(list)
        self._verifier = SignatureVerifier()
        self._manifest_validator = ManifestValidator()

    def register_developer_signing_secret(self, developer_id: str, secret: str) -> None:
        self._verifier.register_developer_secret(developer_id, secret)

    def publish(self, developer_id: str, upload: PackageUpload) -> AgentPackage:
        if upload.namespace != developer_id:
            raise AuthorizationError("developer can only publish to own namespace")
        self._manifest_validator.validate(upload.manifest)
        payload_digest = self._verifier.verify_upload(developer_id, upload)
        key = (upload.namespace, upload.package_id, upload.version)
        if key in self._packages:
            raise ConflictError("package version already exists")

        package = AgentPackage(
            package_id=upload.package_id,
            version=upload.version,
            developer_id=developer_id,
            namespace=upload.namespace,
            category=upload.category,
            permissions=upload.permissions,
            manifest=upload.manifest,
            payload_digest=payload_digest,
            signature=upload.signature,
        )
        self._packages[key] = package
        self._latest_by_package[(upload.namespace, upload.package_id)] = package
        return package

    def list_packages(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        required_permissions: set[str] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        if page < 1 or page_size < 1:
            raise ValidationError("page and page_size must be positive")

        latest_packages = list(self._latest_by_package.values())
        filtered = []
        for package in latest_packages:
            if query and query.lower() not in package.package_id.lower():
                continue
            if category and package.category != category:
                continue
            if required_permissions and not required_permissions.issubset(set(package.permissions)):
                continue
            filtered.append(package)

        total = len(filtered)
        total_pages = max(1, ceil(total / page_size))
        start = (page - 1) * page_size
        end = start + page_size
        page_items = filtered[start:end]
        return {
            "items": [asdict(p) for p in page_items],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def get_package(self, namespace: str, package_id: str, version: str | None = None) -> AgentPackage:
        if version is None:
            package = self._latest_by_package.get((namespace, package_id))
            if package is None:
                raise NotFoundError("package not found")
            return package
        package = self._packages.get((namespace, package_id, version))
        if package is None:
            raise NotFoundError("package version not found")
        return package

    def install(self, tenant_id: str, user_id: str, namespace: str, package_id: str, version: str | None = None) -> InstallRecord:
        package = self.get_package(namespace, package_id, version)
        record = InstallRecord(tenant_id=tenant_id, user_id=user_id, package_fqid=package.fqid)
        self._installs.append(record)
        self._installs_by_tenant[tenant_id].append(record)
        return record

    def list_installs(self, tenant_id: str) -> list[InstallRecord]:
        return list(self._installs_by_tenant[tenant_id])
