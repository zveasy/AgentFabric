from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.errors import AuthorizationError, ValidationError
from agentfabric.events import EventStore
from agentfabric.marketplace import PackageDependency, PackageManifest, PackageMetadata, PackageSignature, SigningKey, TrustedPublisherRegistry
from agentfabric.marketplace.dependencies import DependencyResolver
from agentfabric.marketplace.licensing import Entitlement, LicenseChecker
from agentfabric.marketplace.packages import PackageVersion
from agentfabric.marketplace.registry import InstallService, MarketplaceRegistryService, PublishService
from agentfabric.marketplace.scanning import MarketplaceScanner
from agentfabric.marketplace.signing import SignatureVerifier
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings


def signed_manifest(package_id: str = "research-pack", version: str = "1.0.0", tenant_id: str = "tenant-a") -> tuple[PackageManifest, SigningKey, str]:
    manifest = PackageManifest(
        package_id=package_id,
        name=package_id,
        version=version,
        publisher_tenant_id=tenant_id,
        agent_identity_id=f"{package_id}-agent",
        tool_permissions=("tool.web.search",),
    )
    key = SigningKey(publisher_id=tenant_id, secret="secret")
    signature = PackageSignature.sign(manifest.manifest_hash(), key).signature
    return manifest, key, signature


class Generation6MarketplaceServiceTests(unittest.TestCase):
    def test_manifest_validation_and_signing(self) -> None:
        manifest, key, signature = signed_manifest()
        manifest.validate()
        trusted = TrustedPublisherRegistry()
        trusted.trust("tenant-a", key.fingerprint)
        verifier = SignatureVerifier(trusted)
        self.assertEqual(verifier.verify(publisher_id="tenant-a", manifest_hash=manifest.manifest_hash(), signature=signature, key=key), key.fingerprint)
        with self.assertRaises(ValidationError):
            verifier.verify(publisher_id="tenant-a", manifest_hash=manifest.manifest_hash(), signature="bad", key=key)

    def test_publish_install_uninstall_upgrade_rollback_and_events(self) -> None:
        store = MemoryPersistenceStore()
        events = EventStore(persistence=store)
        registry = MarketplaceRegistryService(store)
        trusted = TrustedPublisherRegistry()
        verifier = SignatureVerifier(trusted)
        publish = PublishService(registry=registry, verifier=verifier, event_store=events)
        install = InstallService(registry=registry, persistence=store, event_store=events)

        manifest, key, signature = signed_manifest(version="1.0.0")
        trusted.trust("tenant-a", key.fingerprint)
        package_v1 = publish.publish(manifest=manifest, metadata=PackageMetadata(), signature=signature, signing_key=key)
        self.assertEqual(package_v1.version, "1.0.0")

        manifest_v2, _, signature_v2 = signed_manifest(version="2.0.0")
        package_v2 = publish.publish(manifest=manifest_v2, metadata=PackageMetadata(), signature=signature_v2, signing_key=key)
        installed = install.install(tenant_id="tenant-b", package_id="research-pack")
        self.assertEqual(installed["version"], "2.0.0")
        install.verify_runtime_entitlement(tenant_id="tenant-b", package_id="research-pack")
        upgraded = install.upgrade(tenant_id="tenant-b", package_id="research-pack", version="2.0.0")
        self.assertEqual(upgraded["version"], "2.0.0")
        rolled = install.rollback(tenant_id="tenant-b", package_id="research-pack", version="1.0.0")
        self.assertEqual(rolled["version"], "1.0.0")
        uninstalled = install.uninstall(tenant_id="tenant-b", package_id="research-pack")
        self.assertFalse(uninstalled["active"])
        self.assertTrue(any(event.event_type == "marketplace.package.installed" for event in events.replay()))
        self.assertEqual(package_v2.package_id, "research-pack")

    def test_dependency_and_scanning_failures(self) -> None:
        manifest, key, signature = signed_manifest()
        package = PackageVersion(
            manifest=manifest,
            manifest_hash=manifest.manifest_hash(),
            signature=signature,
            publisher_fingerprint=key.fingerprint,
        )
        dep_manifest = PackageManifest(
            package_id="unsafe-dep",
            name="Unsafe",
            version="1.0.0",
            publisher_tenant_id="tenant-a",
            agent_identity_id="unsafe",
            tool_permissions=("tenant.data.all",),
        )
        unsafe_dep = PackageVersion(
            manifest=dep_manifest,
            manifest_hash=dep_manifest.manifest_hash(),
            signature=signature,
            publisher_fingerprint=key.fingerprint,
        )
        root_manifest = PackageManifest(
            package_id="root",
            name="Root",
            version="1.0.0",
            publisher_tenant_id="tenant-a",
            agent_identity_id="root",
            dependencies=(PackageDependency("unsafe-dep", "1.x"),),
        )
        root = PackageVersion(
            manifest=root_manifest,
            manifest_hash=root_manifest.manifest_hash(),
            signature=signature,
            publisher_fingerprint=key.fingerprint,
        )
        with self.assertRaises(ValidationError):
            DependencyResolver().resolve(root, {"unsafe-dep": unsafe_dep})

        risky_manifest = PackageManifest(
            package_id="risky",
            name="Risky",
            version="1.0.0",
            publisher_tenant_id="tenant-a",
            agent_identity_id="risky",
            tool_permissions=("network.unbounded",),
        )
        risky = PackageVersion(
            manifest=risky_manifest,
            manifest_hash=risky_manifest.manifest_hash(),
            signature=signature,
            publisher_fingerprint=key.fingerprint,
        )
        self.assertTrue(MarketplaceScanner().scan(risky)["permission"]["requires_approval"])
        self.assertFalse(MarketplaceScanner().scan(package)["permission"]["requires_approval"])

    def test_circular_dependency_rejection_and_entitlement(self) -> None:
        manifest_a = PackageManifest(
            package_id="a",
            name="A",
            version="1.0.0",
            publisher_tenant_id="tenant-a",
            agent_identity_id="a",
            dependencies=(PackageDependency("b", "1.x"),),
        )
        manifest_b = PackageManifest(
            package_id="b",
            name="B",
            version="1.0.0",
            publisher_tenant_id="tenant-a",
            agent_identity_id="b",
            dependencies=(PackageDependency("a", "1.x"),),
        )
        key = SigningKey("tenant-a", "secret")
        pkg_a = PackageVersion(manifest_a, manifest_a.manifest_hash(), "sig", key.fingerprint)
        pkg_b = PackageVersion(manifest_b, manifest_b.manifest_hash(), "sig", key.fingerprint)
        with self.assertRaises(ValidationError):
            DependencyResolver().resolve(pkg_a, {"b": pkg_b, "a": pkg_a})
        LicenseChecker().verify(Entitlement(tenant_id="tenant-a", package_id="a", version="1.0.0", license_type="free"))
        with self.assertRaises(AuthorizationError):
            LicenseChecker().verify(None)


class Generation6MarketplaceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "api.db"
        self.client = TestClient(
            create_app(
                Settings(
                    database_url=f"sqlite:///{db_path}",
                    production_db_path=str(Path(self.tmp.name) / "prod.db"),
                    redis_url="memory://",
                    jwt_secret="test-secret",
                    bootstrap_token="bootstrap-test-token",
                )
            )
        )
        register = self.client.post(
            "/auth/principals/register",
            json={"principal_id": "owner-a", "tenant_id": "tenant-a", "role": "owner", "scopes": []},
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        self.assertEqual(register.status_code, 200)
        token = self.client.post(
            "/auth/token/issue",
            json={"principal_id": "owner-a"},
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        self.headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
        self.client.post(
            "/tenants",
            json={"tenant_id": "tenant-a", "organization_id": "org-a", "name": "Tenant A", "billing_plan": "enterprise"},
            headers=self.headers,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def publish_payload(self, package_id: str = "api-pack", version: str = "1.0.0", **extra) -> dict:
        payload = {
            "package_id": package_id,
            "name": package_id,
            "version": version,
            "agent_identity_id": f"{package_id}-agent",
            "tool_permissions": ["tool.web.search"],
            "signing_secret": "secret",
        }
        payload.update(extra)
        return payload

    def test_marketplace_publish_install_review_reputation_and_audit(self) -> None:
        publish = self.client.post("/marketplace/packages", json=self.publish_payload(), headers=self.headers)
        self.assertEqual(publish.status_code, 200)
        self.assertEqual(publish.json()["package_id"], "api-pack")

        listed = self.client.get("/marketplace/packages", headers=self.headers)
        self.assertEqual(listed.json()["total"], 1)
        detail = self.client.get("/marketplace/packages/api-pack", headers=self.headers)
        self.assertEqual(detail.status_code, 200)
        risk = self.client.get("/marketplace/packages/api-pack/risk", headers=self.headers)
        self.assertFalse(risk.json()["permission"]["requires_approval"])

        install = self.client.post("/marketplace/packages/api-pack/install", json={}, headers=self.headers)
        self.assertEqual(install.status_code, 200)
        self.assertEqual(self.client.get("/marketplace/installed", headers=self.headers).json()["items"][0]["package_id"], "api-pack")

        review = self.client.post(
            "/marketplace/packages/api-pack/reviews",
            json={"rating": 5, "review": "solid"},
            headers=self.headers,
        )
        self.assertEqual(review.status_code, 200)
        reputation = self.client.get("/marketplace/publishers/tenant-a/reputation", headers=self.headers)
        self.assertEqual(reputation.status_code, 200)
        self.assertEqual(reputation.json()["package_count"], 1)

        audit = self.client.get("/tenants/tenant-a/audit-export", headers=self.headers)
        event_types = {item["event_type"] for item in audit.json()["events"]}
        self.assertIn("marketplace.package.installed", event_types)

    def test_upgrade_rollback_uninstall_and_metering(self) -> None:
        self.client.post("/marketplace/packages", json=self.publish_payload(version="1.0.0"), headers=self.headers)
        self.client.post("/marketplace/packages/api-pack/versions", json=self.publish_payload(version="2.0.0"), headers=self.headers)
        self.client.post("/marketplace/packages/api-pack/install", json={"version": "1.0.0"}, headers=self.headers)
        upgraded = self.client.post("/marketplace/packages/api-pack/upgrade", json={"version": "2.0.0"}, headers=self.headers)
        self.assertEqual(upgraded.json()["version"], "2.0.0")
        rolled = self.client.post("/marketplace/packages/api-pack/rollback", json={"version": "1.0.0"}, headers=self.headers)
        self.assertEqual(rolled.json()["version"], "1.0.0")
        uninstalled = self.client.post("/marketplace/packages/api-pack/uninstall", headers=self.headers)
        self.assertFalse(uninstalled.json()["active"])
        usage = self.client.get("/tenants/tenant-a/usage", headers=self.headers)
        self.assertGreaterEqual(usage.json()["usage"]["marketplace_installs"], 1)

    def test_api_rejects_unsafe_unsigned_and_missing_entitlement_review(self) -> None:
        unsafe = self.client.post(
            "/marketplace/packages",
            json=self.publish_payload(package_id="unsafe", tool_permissions=["network.unbounded"]),
            headers=self.headers,
        )
        self.assertEqual(unsafe.status_code, 400)
        bad_review = self.client.post(
            "/marketplace/packages/missing/reviews",
            json={"rating": 1},
            headers=self.headers,
        )
        self.assertEqual(bad_review.status_code, 403)


if __name__ == "__main__":
    unittest.main()
