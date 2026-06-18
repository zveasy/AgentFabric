from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.config import ProductionSafetyError, validate_production_safety
from agentfabric.events import EventStore
from agentfabric.federation import FederatedOrg, FederationService, RemoteDelegation, TrustAgreement
from agentfabric.marketplace import PackageManifest, PackageSignature, SigningKey, TrustedPublisherRegistry
from agentfabric.marketplace.signing import SignatureVerifier
from agentfabric.memory import DurableMemoryStore
from agentfabric.migrations import MigrationRunner
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings
from veil_client import MockVeilClient


class Generation10ReleaseTests(unittest.TestCase):
    def test_production_config_fails_closed_and_dev_exceptions(self) -> None:
        with self.assertRaises(ValueError):
            Settings(environment="production", jwt_secret="change-me")
        unsafe = Settings(
            environment="production",
            jwt_secret="x" * 40,
            database_url="sqlite:///unsafe.db",
            strict_signing=False,
        )
        with self.assertRaises(ProductionSafetyError):
            validate_production_safety(unsafe)
        dev = Settings(environment="development", jwt_secret="dev", database_url="sqlite:///dev.db", strict_signing=False)
        self.assertTrue(validate_production_safety(dev))

    def test_structured_errors_tenantless_rejection_and_raw_sensitive_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(
                create_app(
                    Settings(
                        database_url=f"sqlite:///{Path(tmp) / 'api.db'}",
                        production_db_path=str(Path(tmp) / "prod.db"),
                        redis_url="memory://",
                        jwt_secret="test-secret",
                        bootstrap_token="bootstrap-test-token",
                    )
                )
            )
            response = client.get("/agents")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["error"]["code"], "auth_failure")

            register = client.post(
                "/auth/principals/register",
                json={"principal_id": "owner-a", "tenant_id": "tenant-a", "role": "owner", "scopes": []},
                headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
            )
            self.assertEqual(register.status_code, 200)
            token = client.post(
                "/auth/token/issue",
                json={"principal_id": "owner-a"},
                headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
            )
            headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
            client.post("/tenants", json={"tenant_id": "tenant-a", "organization_id": "org-a", "name": "Tenant A"}, headers=headers)
            raw = client.post("/memory/agent-a", json={"content": {"secret": "raw-value"}}, headers=headers)
            self.assertEqual(raw.status_code, 400)
            self.assertEqual(raw.json()["error"]["code"], "validation_error")

    def test_openapi_export_is_deterministic_and_includes_new_apis(self) -> None:
        subprocess.run([sys.executable, "scripts/export_openapi.py"], check=True)
        first = Path("docs/api/openapi.json").read_text(encoding="utf-8")
        subprocess.run([sys.executable, "scripts/export_openapi.py"], check=True)
        second = Path("docs/api/openapi.json").read_text(encoding="utf-8")
        self.assertEqual(first, second)
        schema = json.loads(first)
        self.assertIn("/federation/messages/send", schema["paths"])
        self.assertIn("/runtime/jobs", schema["paths"])
        self.assertIn("/governance/proposals", schema["paths"])

    def test_release_script_exists_and_contains_required_gates(self) -> None:
        script = Path("scripts/release_validate.py").read_text(encoding="utf-8")
        for expected in ["ruff", "pytest", "unittest", "scripts/export_openapi.py"]:
            self.assertIn(expected, script)

    def test_migration_dry_run_event_integrity_unsigned_package_and_memory_safety(self) -> None:
        store = MemoryPersistenceStore()
        dry = MigrationRunner(store).apply(dry_run=True)
        self.assertEqual(dry["current_version"], 0)

        events = EventStore(persistence=store)
        event = events.append("workflow.started", "wf", {"tenant_id": "tenant-a"})
        corrupt = event.as_dict()
        corrupt["event_hash"] = "bad"
        store.put("events", event.event_id, corrupt)
        self.assertFalse(EventStore(persistence=store).validate_integrity())

        manifest = PackageManifest("pkg", "Pkg", "1.0.0", "tenant-a", "agent-a")
        key = SigningKey("tenant-a", "secret")
        trusted = TrustedPublisherRegistry()
        trusted.trust("tenant-a", key.fingerprint)
        verifier = SignatureVerifier(trusted, allow_unsigned_local=False)
        with self.assertRaises(Exception):
            verifier.verify("tenant-a", manifest.manifest_hash(), "", key)
        signature = PackageSignature.sign(manifest.manifest_hash(), key)
        self.assertTrue(signature.signature)

        memory = DurableMemoryStore(MemoryPersistenceStore())
        with self.assertRaises(ValueError):
            memory.create(owner_agent_id="agent", tenant_id="tenant-a", content={"raw": "value"})

    def test_federation_without_active_trust_and_veil_readiness_failure(self) -> None:
        store = MemoryPersistenceStore()
        events = EventStore(persistence=store)
        federation = FederationService(persistence=store, event_store=events, veil_client=MockVeilClient())
        federation.create_org(FederatedOrg("tenant-a", "org-a", "remote", "Remote", "https://remote", "key", "owner"))
        agreement = federation.create_agreement(
            TrustAgreement("tenant-a", "org-a", "remote", "owner", allowed_capabilities=("research",))
        )
        with self.assertRaises(Exception):
            federation.request_delegation(
                RemoteDelegation("tenant-a", "org-a", agreement.agreement_id, "remote", "agent-a", "remote-a", "research", {"veil_reference": "ref"}, "owner"),
                signing_secret="secret",
                governance_approved=True,
            )
        unsafe = Settings(environment="production", jwt_secret="x" * 40, database_url="postgresql://db", cloud_queue_backend="redis", strict_signing=True, redis_url="redis://redis:6379/0")
        with self.assertRaises(ProductionSafetyError):
            validate_production_safety(unsafe)


if __name__ == "__main__":
    unittest.main()
