"""Package version record."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .package_manifest import PackageManifest
from .package_metadata import PackageMetadata


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class PackageVersion:
    manifest: PackageManifest
    manifest_hash: str
    signature: str
    publisher_fingerprint: str
    metadata: PackageMetadata = field(default_factory=PackageMetadata)
    created_at: datetime = field(default_factory=utc_now)
    published_at: datetime = field(default_factory=utc_now)

    @property
    def package_id(self) -> str:
        return self.manifest.package_id

    @property
    def version(self) -> str:
        return self.manifest.version

    @property
    def key(self) -> str:
        return f"{self.package_id}:{self.version}"

    def as_dict(self) -> dict[str, object]:
        return {
            "package_id": self.package_id,
            "name": self.manifest.name,
            "version": self.version,
            "publisher_tenant_id": self.manifest.publisher_tenant_id,
            "agent_identity_id": self.manifest.agent_identity_id,
            "manifest_hash": self.manifest_hash,
            "runtime_requirements": dict(self.manifest.runtime_requirements),
            "tool_permissions": list(self.manifest.tool_permissions),
            "connector_requirements": list(self.manifest.connector_requirements),
            "connector_permissions": list(self.manifest.connector_permissions),
            "dependencies": [item.as_dict() for item in self.manifest.dependencies],
            "license_type": self.manifest.license_type,
            "pricing_model": self.manifest.pricing_model,
            "signature": self.signature,
            "publisher_fingerprint": self.publisher_fingerprint,
            "metadata": self.metadata.as_dict(),
            "created_at": self.created_at.isoformat(),
            "published_at": self.published_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "PackageVersion":
        manifest = PackageManifest.from_dict(value)
        return cls(
            manifest=manifest,
            manifest_hash=str(value["manifest_hash"]),
            signature=str(value.get("signature", "")),
            publisher_fingerprint=str(value.get("publisher_fingerprint", "")),
            metadata=PackageMetadata.from_dict(dict(value.get("metadata", {}))),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            published_at=datetime.fromisoformat(str(value["published_at"])),
        )
