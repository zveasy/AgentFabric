from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.audit_bundle import AuditBundleExporter, contains_raw_sensitive
from agentfabric.cloud import CloudRuntime
from agentfabric.cloud.queue_backends import MemoryJobQueue
from agentfabric.connectors import ConnectorCredentials, ConnectorManifest, ConnectorPolicy, ConnectorRegistry
from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError, ValidationError
from agentfabric.events import EventStore
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings
from veil_client import AuditEventResponse, MockVeilClient, PolicyCheckResponse, SanitizeContextResponse


class SpyVeilClient(MockVeilClient):
    def __init__(self) -> None:
        self.sanitize_calls = 0
        self.policy_calls = 0
        self.audit_calls = 0

    def sanitize_context(self, request):
        self.sanitize_calls += 1
        sanitized = dict(request.context)
        if "content" in sanitized:
            sanitized["content"] = "sanitized"
        sanitized["veil_token_refs"] = ("veil-token-connector",)
        return SanitizeContextResponse(sanitized_context=sanitized, redactions=("content",))

    def check_policy(self, request):
        self.policy_calls += 1
        return PolicyCheckResponse(allowed=True)

    def create_audit_event(self, request):
        self.audit_calls += 1
        return AuditEventResponse(event_id=f"audit:{request.event_type}", accepted=True)


class DenyVeilClient(SpyVeilClient):
    def check_policy(self, request):
        self.policy_calls += 1
        return PolicyCheckResponse(allowed=False, reason="connector denied")


class Generation12ConnectorServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryPersistenceStore()
        self.events = EventStore(persistence=self.store)
        self.veil = SpyVeilClient()
        self.runtime = CloudRuntime(queue=MemoryJobQueue(), persistence=self.store, event_store=self.events, veil_client=self.veil)
        self.registry = ConnectorRegistry(
            persistence=self.store,
            event_store=self.events,
            veil_client=self.veil,
            runtime=self.runtime,
        )
        self.ctx = TenantContext(
            tenant_id="tenant-a",
            organization_id="org-a",
            principal_id="owner-a",
            roles=("owner",),
        )

    def connector(self):
        return self.registry.register(
            ctx=self.ctx,
            manifest=ConnectorManifest(
                connector_type="slack",
                display_name="Pilot Slack",
                scopes=("channels:read",),
                data_classes=("messages",),
                webhook_supported=True,
            ),
            credentials=ConnectorCredentials(credential_ref="veil-credential-ref:slack", provider="slack"),
            policy=ConnectorPolicy(allowed_data_classes=("messages",)),
            connector_id="connector-slack",
        )

    def test_connector_registration_credentials_and_health(self) -> None:
        connector = self.connector()
        self.assertEqual(connector.connector_id, "connector-slack")
        stored = self.store.get("connectors", connector.connector_id)
        self.assertEqual(stored["credentials"]["credential_ref"], "veil-credential-ref:slack")
        self.assertNotIn("secret", stored["credentials"])
        health = self.registry.health(ctx=self.ctx, connector_id=connector.connector_id)
        self.assertEqual(health["status"], "active")
        self.assertTrue(health["credential_ref_present"])

    def test_sync_search_fetch_jobs_and_veil_mediation(self) -> None:
        connector = self.connector()
        sync_job = self.registry.create_job(
            ctx=self.ctx,
            connector_id=connector.connector_id,
            operation="sync",
            payload={"data_class": "messages", "query_ref": "veil-query-ref"},
        )
        self.assertEqual(sync_job.job_type, "connector_sync")

        result = self.registry.execute(
            ctx=self.ctx,
            connector_id=connector.connector_id,
            operation="search",
            payload={"data_class": "messages", "content": "raw text to sanitize"},
        )
        self.assertEqual(result.sanitized_payload["content"], "sanitized")
        self.assertEqual(result.token_refs, ("veil-token-connector",))
        self.assertEqual(self.veil.policy_calls, 1)
        self.assertEqual(self.veil.sanitize_calls, 1)
        self.assertEqual(self.veil.audit_calls, 1)
        self.assertTrue(any(event.event_type == "connector.operation.completed" for event in self.events.replay()))

    def test_veil_denial_tenant_isolation_and_raw_data_rejection(self) -> None:
        connector = self.connector()
        other_ctx = TenantContext("tenant-b", "org-b", "owner-b", ("owner",))
        with self.assertRaises(AuthorizationError):
            self.registry.get(other_ctx, connector.connector_id)
        with self.assertRaises(ValidationError):
            self.registry.execute(ctx=self.ctx, connector_id=connector.connector_id, operation="search", payload={"raw": "secret"})

        denied = ConnectorRegistry(
            persistence=self.store,
            event_store=self.events,
            veil_client=DenyVeilClient(),
            runtime=self.runtime,
        )
        with self.assertRaises(AuthorizationError):
            denied.execute(
                ctx=self.ctx,
                connector_id=connector.connector_id,
                operation="search",
                payload={"data_class": "messages", "query_ref": "veil-query-ref"},
            )

    def test_audit_bundle_includes_connector_activity_without_raw_values(self) -> None:
        connector = self.connector()
        self.registry.execute(
            ctx=self.ctx,
            connector_id=connector.connector_id,
            operation="fetch",
            payload={"data_class": "messages", "document_ref": "veil-doc-ref"},
        )
        bundle = AuditBundleExporter(persistence=self.store, event_store=self.events).export("tenant-a").as_dict()
        self.assertEqual(bundle["connectors"][0]["connector_id"], connector.connector_id)
        self.assertEqual(bundle["connector_results"][0]["veil_audit_id"], "audit:connector.fetch")
        self.assertFalse(contains_raw_sensitive(bundle))


class Generation12ConnectorApiTests(unittest.TestCase):
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
        tenant = self.client.post(
            "/tenants",
            json={"tenant_id": "tenant-a", "organization_id": "org-a", "name": "Tenant A", "billing_plan": "enterprise"},
            headers=self.headers,
        )
        self.assertEqual(tenant.status_code, 200)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_connector_api_registration_sync_search_fetch_webhook_health_and_auth(self) -> None:
        created = self.client.post(
            "/connectors",
            json={
                "connector_id": "connector-github",
                "connector_type": "github",
                "display_name": "GitHub",
                "scopes": ["repo:read"],
                "data_classes": ["issues"],
                "webhook_supported": True,
                "credentials": {"credential_ref": "veil-credential-ref:github", "provider": "github"},
                "policy": {"allowed_data_classes": ["issues"]},
            },
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["connector_id"], "connector-github")
        self.assertEqual(created.json()["credentials"]["credential_ref"], "veil-credential-ref:github")

        self.assertEqual(self.client.get("/connectors", headers=self.headers).json()["total"], 1)
        self.assertEqual(self.client.get("/connectors/connector-github", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get("/connectors/connector-github/health", headers=self.headers).json()["status"], "active")

        search = self.client.post(
            "/connectors/connector-github/search",
            json={"data_class": "issues", "query_ref": "veil-query-ref"},
            headers=self.headers,
        )
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()["job"]["job_type"], "connector_search")
        self.assertIn("veil_audit_id", search.json()["result"])

        fetch = self.client.post(
            "/connectors/connector-github/fetch",
            json={"data_class": "issues", "document_ref": "veil-doc-ref"},
            headers=self.headers,
        )
        self.assertEqual(fetch.json()["job"]["job_type"], "connector_document_fetch")

        sync = self.client.post(
            "/connectors/connector-github/sync",
            json={"data_class": "issues", "cursor_ref": "veil-cursor-ref"},
            headers=self.headers,
        )
        self.assertEqual(sync.json()["job"]["job_type"], "connector_sync")

        webhook = self.client.post(
            "/connectors/connector-github/webhook",
            json={"data_class": "issues", "event_ref": "veil-event-ref"},
            headers=self.headers,
        )
        self.assertEqual(webhook.json()["job"]["job_type"], "connector_webhook_handling")

        raw = self.client.post(
            "/connectors/connector-github/search",
            json={"data_class": "issues", "raw": "secret"},
            headers=self.headers,
        )
        self.assertEqual(raw.status_code, 400)
        self.assertEqual(self.client.get("/connectors").status_code, 401)


if __name__ == "__main__":
    unittest.main()
