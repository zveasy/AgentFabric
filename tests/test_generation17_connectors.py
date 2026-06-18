from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agent_connectors import (
    ConnectorAudit,
    ConnectorExecutionPolicy,
    ConnectorExecutionService,
    ConnectorManifest,
    ConnectorRegistry,
    ConnectorSandbox,
    CredentialVault,
)
from agentfabric.audit_bundle import AuditBundleExporter, contains_raw_sensitive
from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError
from agentfabric.events import EventStore
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings
from veil_client import MockVeilClient


class Generation17ConnectorServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryPersistenceStore()
        self.events = EventStore(persistence=self.store)
        self.audit = ConnectorAudit(self.events)
        self.registry = ConnectorRegistry(self.store, self.audit)
        self.vault = CredentialVault(self.store)
        self.ctx = TenantContext("tenant-a", "org-a", "owner-a", ())
        self.manifest = ConnectorManifest(
            connector_id="github-enterprise",
            name="GitHub Enterprise",
            version="1.0.0",
            description="Repository operations",
            connector_type="github",
            supported_actions=("read", "write"),
            required_permissions=("github.read", "github.write"),
            credential_type="oauth",
            rate_limits={"requests_per_minute": 2},
            risk_level="medium",
            allowed_domains=("github.example.com",),
            allowed_http_methods=("GET", "POST"),
            trust_score=0.95,
        )

    def enabled_service(self, *, sandbox: ConnectorSandbox | None = None, production: bool = False, veil=MockVeilClient()):
        self.registry.register(self.manifest, tenant_id="tenant-a", created_by="owner-a")
        credential = self.vault.create(
            tenant_id="tenant-a",
            connector_id=self.manifest.connector_id,
            credential_type="oauth",
            created_by="owner-a",
            secret="development-secret",
        )
        policy = ConnectorExecutionPolicy(
            policy_id="github-policy",
            tenant_id="tenant-a",
            allowed_agents=("agent-a",),
            allowed_connectors=(self.manifest.connector_id,),
            allowed_actions=("read", "write"),
            allowed_credential_types=("oauth",),
            maximum_risk="medium",
            minimum_package_trust_score=0.8,
        )
        self.registry.enable(
            self.ctx,
            self.manifest.connector_id,
            version="1.0.0",
            credential_ref=credential.reference_id,
            policy=policy,
        )
        return ConnectorExecutionService(
            persistence=self.store,
            registry=self.registry,
            vault=self.vault,
            audit=self.audit,
            veil_client=veil,
            production=production,
            sandbox=sandbox,
        )

    def test_manifest_registration_versioning_enable_disable_and_validation(self) -> None:
        registered = self.registry.register(self.manifest, tenant_id="tenant-a", created_by="owner-a")
        self.assertEqual(registered.version, "1.0.0")
        version_two = ConnectorManifest.from_dict({**self.manifest.as_dict(), "version": "2.0.0"})
        self.registry.register(version_two, tenant_id="tenant-a", created_by="owner-a")
        self.assertEqual(self.registry.get(self.ctx, self.manifest.connector_id).version, "2.0.0")
        invalid = ConnectorManifest.from_dict({**self.manifest.as_dict(), "required_permissions": []})
        with self.assertRaises(ValueError):
            invalid.validate()

    def test_credential_isolation_execution_permissions_policy_and_audit_bundle(self) -> None:
        service = self.enabled_service()
        result = service.execute(
            ctx=self.ctx,
            connector_id=self.manifest.connector_id,
            agent_id="agent-a",
            action="read",
            payload={"url": "https://github.example.com/repos/one", "method": "GET"},
            agent_permissions={"github.read"},
            package_trust_score=0.9,
        )
        self.assertEqual(result.status, "completed")
        self.assertNotIn("development-secret", str(result.as_dict()))
        with self.assertRaises(AuthorizationError):
            service.execute(
                ctx=self.ctx,
                connector_id=self.manifest.connector_id,
                agent_id="agent-a",
                action="write",
                payload={"url": "https://github.example.com/repos/one", "method": "POST"},
                agent_permissions={"github.read"},
            )
        credential_id = result.credential_ref.split(":")[1]
        with self.assertRaises(AuthorizationError):
            self.vault.get("tenant-b", credential_id)

        bundle = AuditBundleExporter(persistence=self.store, event_store=self.events).export("tenant-a").as_dict()
        self.assertEqual(bundle["connector_manifests"][0]["connector_id"], self.manifest.connector_id)
        self.assertTrue(bundle["connector_enablement"])
        self.assertTrue(bundle["connector_executions"])
        self.assertTrue(bundle["connector_denials"])
        self.assertTrue(bundle["credential_lifecycle"])
        self.assertTrue(bundle["connector_policies"])
        self.assertFalse(contains_raw_sensitive(bundle))

    def test_rate_limits_payload_limits_blocked_domains_and_production_fail_closed(self) -> None:
        service = self.enabled_service(sandbox=ConnectorSandbox(max_payload_bytes=100))
        valid = {
            "url": "https://github.example.com/r",
            "method": "GET",
        }
        service.execute(
            ctx=self.ctx,
            connector_id=self.manifest.connector_id,
            agent_id="agent-a",
            action="read",
            payload=valid,
            agent_permissions={"github.read"},
        )
        service.execute(
            ctx=self.ctx,
            connector_id=self.manifest.connector_id,
            agent_id="agent-a",
            action="read",
            payload=valid,
            agent_permissions={"github.read"},
        )
        with self.assertRaises(AuthorizationError):
            service.execute(
                ctx=self.ctx,
                connector_id=self.manifest.connector_id,
                agent_id="agent-a",
                action="read",
                payload=valid,
                agent_permissions={"github.read"},
            )

        with self.assertRaises(ValueError):
            service.sandbox.validate_request(
                {"url": "http://localhost/private", "method": "GET"},
                allowed_domains=(),
                allowed_methods=("GET",),
            )
        with self.assertRaises(ValueError):
            service.sandbox.validate_request(
                {"url": "https://github.example.com/r", "method": "GET", "data": "x" * 200},
                allowed_domains=("github.example.com",),
                allowed_methods=("GET",),
            )

        isolated_store = MemoryPersistenceStore()
        isolated_events = EventStore(persistence=isolated_store)
        isolated_audit = ConnectorAudit(isolated_events)
        isolated_registry = ConnectorRegistry(isolated_store, isolated_audit)
        isolated_vault = CredentialVault(isolated_store)
        isolated_registry.register(self.manifest, tenant_id="tenant-a", created_by="owner-a")
        credential = isolated_vault.create(
            tenant_id="tenant-a",
            connector_id=self.manifest.connector_id,
            credential_type="oauth",
            created_by="owner-a",
            secret="secret",
        )
        isolated_registry.enable(
            self.ctx,
            self.manifest.connector_id,
            version="1.0.0",
            credential_ref=credential.reference_id,
            policy=ConnectorExecutionPolicy(
                "policy-production",
                "tenant-a",
                allowed_agents=("agent-a",),
                allowed_connectors=(self.manifest.connector_id,),
                allowed_actions=("read",),
                allowed_credential_types=("oauth",),
            ),
        )
        production = ConnectorExecutionService(
            persistence=isolated_store,
            registry=isolated_registry,
            vault=isolated_vault,
            audit=isolated_audit,
            veil_client=None,
            production=True,
        )
        with self.assertRaises(AuthorizationError):
            production.execute(
                ctx=self.ctx,
                connector_id=self.manifest.connector_id,
                agent_id="agent-a",
                action="read",
                payload=valid,
                agent_permissions={"github.read"},
            )


class Generation17ConnectorApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.client = TestClient(
            create_app(
                Settings(
                    database_url=f"sqlite:///{Path(self.tmp.name) / 'api.db'}",
                    jwt_secret="test-secret",
                    bootstrap_token="bootstrap-test-token",
                    cloud_queue_backend="memory",
                )
            )
        )
        self.client.post(
            "/auth/principals/register",
            json={"principal_id": "owner-a", "tenant_id": "tenant-a", "role": "owner", "scopes": []},
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
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

    def register_connector(self, *, risk: str = "medium", trust: float = 0.95) -> None:
        response = self.client.post(
            "/connectors/register",
            json={
                "connector_id": "github-enterprise",
                "name": "GitHub Enterprise",
                "version": "1.0.0",
                "description": "Repository operations",
                "connector_type": "github",
                "supported_actions": ["read", "write"],
                "required_permissions": ["github.read", "github.write"],
                "credential_type": "oauth",
                "rate_limits": {"requests_per_minute": 10},
                "risk_level": risk,
                "tenant_scope": "tenant",
                "allowed_domains": ["github.example.com"],
                "allowed_http_methods": ["GET", "POST"],
                "trust_score": trust,
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)

    def test_connector_api_lifecycle_execution_rbac_and_marketplace_gates(self) -> None:
        self.assertEqual(self.client.get("/connectors").status_code, 401)
        self.register_connector(risk="high")
        credential = self.client.post(
            "/credentials",
            json={
                "connector_id": "github-enterprise",
                "credential_type": "oauth",
                "secret": "api-secret",
            },
            headers=self.headers,
        )
        self.assertEqual(credential.status_code, 200)
        self.assertNotIn("api-secret", credential.text)
        credential_id = credential.json()["credential_id"]
        enabled = self.client.post(
            "/connectors/github-enterprise/enable",
            json={
                "credential_id": credential_id,
                "allowed_agents": ["agent-a"],
                "allowed_actions": ["read", "write"],
                "maximum_risk": "high",
            },
            headers=self.headers,
        )
        self.assertEqual(enabled.status_code, 200)
        executed = self.client.post(
            "/connectors/github-enterprise/execute",
            json={
                "agent_id": "agent-a",
                "action": "read",
                "payload": {"url": "https://github.example.com/repo", "method": "GET"},
            },
            headers=self.headers,
        )
        self.assertEqual(executed.status_code, 200)
        self.assertEqual(executed.json()["status"], "completed")
        denied = self.client.post(
            "/connectors/github-enterprise/execute",
            json={
                "agent_id": "agent-b",
                "action": "read",
                "payload": {"url": "https://github.example.com/repo", "method": "GET"},
            },
            headers=self.headers,
        )
        self.assertEqual(denied.status_code, 403)

        undeclared = self.client.post(
            "/marketplace/packages",
            json={
                "package_id": "pkg-undeclared",
                "name": "Undeclared",
                "version": "1.0.0",
                "agent_identity_id": "agent-a",
                "tool_permissions": ["github.read"],
            },
            headers=self.headers,
        )
        self.assertEqual(undeclared.status_code, 403)
        risky = self.client.post(
            "/marketplace/packages",
            json={
                "package_id": "pkg-risky",
                "name": "Risky",
                "version": "1.0.0",
                "agent_identity_id": "agent-a",
                "connector_requirements": ["github-enterprise"],
                "connector_permissions": ["github.read"],
                "tool_permissions": ["github.read"],
            },
            headers=self.headers,
        )
        self.assertEqual(risky.status_code, 403)
        disabled = self.client.post("/connectors/github-enterprise/disable", headers=self.headers)
        self.assertEqual(disabled.status_code, 200)
        rotated = self.client.post(
            f"/credentials/{credential_id}/rotate",
            json={"secret": "rotated-secret"},
            headers=self.headers,
        )
        self.assertEqual(rotated.json()["version"], 2)
        revoked = self.client.post(f"/credentials/{credential_id}/revoke", headers=self.headers)
        self.assertEqual(revoked.json()["status"], "revoked")


if __name__ == "__main__":
    unittest.main()
