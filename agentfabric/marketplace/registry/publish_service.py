"""Marketplace package publish flow."""

from __future__ import annotations

from agentfabric.events import EventStore
from agentfabric.marketplace.packages import PackageManifest, PackageMetadata, PackageVersion
from agentfabric.marketplace.scanning import MarketplaceScanner
from agentfabric.marketplace.signing import SignatureVerifier, SigningKey

from .registry_service import MarketplaceRegistryService


class PublishService:
    def __init__(
        self,
        *,
        registry: MarketplaceRegistryService,
        verifier: SignatureVerifier,
        event_store: EventStore,
    ) -> None:
        self.registry = registry
        self.verifier = verifier
        self.event_store = event_store

    def publish(
        self,
        *,
        manifest: PackageManifest,
        metadata: PackageMetadata,
        signature: str,
        signing_key: SigningKey,
    ) -> PackageVersion:
        manifest.validate()
        manifest_hash = manifest.manifest_hash()
        fingerprint = self.verifier.verify(
            publisher_id=manifest.publisher_tenant_id,
            manifest_hash=manifest_hash,
            signature=signature,
            key=signing_key,
        )
        package = PackageVersion(
            manifest=manifest,
            manifest_hash=manifest_hash,
            signature=signature,
            publisher_fingerprint=fingerprint,
            metadata=metadata,
        )
        MarketplaceScanner().enforce(package, self.registry.available_by_id())
        self.registry.save_version(package)
        self.event_store.append(
            "marketplace.package.published",
            package.package_id,
            {
                "tenant_id": manifest.publisher_tenant_id,
                "package_id": package.package_id,
                "version": package.version,
                "manifest_hash": manifest_hash,
            },
        )
        self.event_store.append(
            "marketplace.package.signed",
            package.package_id,
            {
                "tenant_id": manifest.publisher_tenant_id,
                "package_id": package.package_id,
                "version": package.version,
                "publisher_fingerprint": fingerprint,
            },
        )
        return package
