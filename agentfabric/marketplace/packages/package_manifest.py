"""Signed marketplace package manifest."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json

from .package_dependency import PackageDependency


@dataclass(frozen=True)
class PackageManifest:
    package_id: str
    name: str
    version: str
    publisher_tenant_id: str
    agent_identity_id: str
    runtime_requirements: dict[str, object] = field(default_factory=dict)
    tool_permissions: tuple[str, ...] = ()
    connector_requirements: tuple[str, ...] = ()
    connector_permissions: tuple[str, ...] = ()
    dependencies: tuple[PackageDependency, ...] = ()
    license_type: str = "free"
    pricing_model: str = "free"

    def validate(self) -> None:
        required = [self.package_id, self.name, self.version, self.publisher_tenant_id, self.agent_identity_id]
        if not all(required):
            raise ValueError("package manifest is missing required fields")
        if any(permission.startswith("raw.") for permission in self.tool_permissions):
            raise ValueError("package cannot request raw sensitive persistence")
        connector_like = {permission for permission in self.tool_permissions if "." in permission and permission.split(".", 1)[0] in {
            "gmail", "calendar", "github", "jira", "slack", "servicenow", "s3", "custom_http", "teams", "salesforce", "sharepoint"
        }}
        if not connector_like.issubset(set(self.connector_permissions)):
            raise ValueError("connector permissions must be explicitly declared")

    def as_dict(self) -> dict[str, object]:
        return {
            "package_id": self.package_id,
            "name": self.name,
            "version": self.version,
            "publisher_tenant_id": self.publisher_tenant_id,
            "agent_identity_id": self.agent_identity_id,
            "runtime_requirements": dict(self.runtime_requirements),
            "tool_permissions": list(self.tool_permissions),
            "connector_requirements": list(self.connector_requirements),
            "connector_permissions": list(self.connector_permissions),
            "dependencies": [item.as_dict() for item in self.dependencies],
            "license_type": self.license_type,
            "pricing_model": self.pricing_model,
        }

    def manifest_hash(self) -> str:
        return sha256(json.dumps(self.as_dict(), sort_keys=True).encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "PackageManifest":
        return cls(
            package_id=str(value["package_id"]),
            name=str(value.get("name", value["package_id"])),
            version=str(value["version"]),
            publisher_tenant_id=str(value["publisher_tenant_id"]),
            agent_identity_id=str(value["agent_identity_id"]),
            runtime_requirements=dict(value.get("runtime_requirements", {})),
            tool_permissions=tuple(str(item) for item in value.get("tool_permissions", ())),
            connector_requirements=tuple(str(item) for item in value.get("connector_requirements", ())),
            connector_permissions=tuple(str(item) for item in value.get("connector_permissions", ())),
            dependencies=tuple(PackageDependency.from_dict(item) for item in value.get("dependencies", ())),
            license_type=str(value.get("license_type", "free")),
            pricing_model=str(value.get("pricing_model", "free")),
        )
