from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.audit_bundle import AuditBundleExporter, contains_raw_sensitive
from agentfabric.cloud import CloudRuntime
from agentfabric.cloud.queue_backends import MemoryJobQueue
from agentfabric.collaboration import ContextStore, MeshWorkflowEngine, TaskGraph, TaskNode
from agentfabric.connectors import ConnectorCredentials, ConnectorManifest, ConnectorPolicy, ConnectorRegistry
from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError, ValidationError
from agentfabric.events import EventStore
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings
from agentfabric.tools import ToolManifest, ToolPermission, ToolRegistry, ToolRouter
from veil_client import AuditEventResponse, MockVeilClient, PolicyCheckResponse, SanitizeContextResponse


class SpyVeilClient(MockVeilClient):
    def __init__(self) -> None:
        self.policy_calls = 0
        self.sanitize_calls = 0
        self.audit_calls = 0

    def check_policy(self, request):
        self.policy_calls += 1
        return PolicyCheckResponse(allowed=True)

    def sanitize_context(self, request):
        self.sanitize_calls += 1
        sanitized = dict(request.context)
        sanitized.setdefault("classification", "internal")
        sanitized.setdefault("veil_token_refs", ("veil-token-tool",))
        if "content" in sanitized:
            sanitized["content"] = "sanitized"
        return SanitizeContextResponse(sanitized_context=sanitized, redactions=("content",))

    def create_audit_event(self, request):
        self.audit_calls += 1
        return AuditEventResponse(event_id=f"audit:{request.event_type}", accepted=True)


class DenyVeilClient(SpyVeilClient):
    def check_policy(self, request):
        self.policy_calls += 1
        return PolicyCheckResponse(allowed=False, reason="tool denied")


class Generation13ToolServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryPersistenceStore()
        self.events = EventStore(persistence=self.store)
        self.veil = SpyVeilClient()
        self.runtime = CloudRuntime(queue=MemoryJobQueue(), persistence=self.store, event_store=self.events, veil_client=self.veil)
        self.connector_registry = ConnectorRegistry(
            persistence=self.store,
            event_store=self.events,
            veil_client=self.veil,
            runtime=self.runtime,
        )
        self.ctx = TenantContext(
            tenant_id="tenant-a",
            organization_id="org-a",
            principal_id="owner-a",
            roles=("tools.read", "tools.manage", "tools.execute", "audit.export"),
        )
        self.connector = self.connector_registry.register(
            ctx=self.ctx,
            manifest=ConnectorManifest("github", "GitHub", data_classes=("issues",), scopes=("repo:read",)),
            credentials=ConnectorCredentials("veil-credential-ref:github", "github"),
            policy=ConnectorPolicy(allowed_data_classes=("issues",)),
            connector_id="connector-github",
        )
        self.registry = ToolRegistry(
            persistence=self.store,
            event_store=self.events,
            veil_client=self.veil,
            router=ToolRouter(
                connector_registry=self.connector_registry,
                audit_exporter=AuditBundleExporter(persistence=self.store, event_store=self.events),
            ),
            runtime=self.runtime,
        )

    def register_tool(self, *, tool_id: str = "tool-github-search", tool_type: str = "connector_search", governance: bool = False):
        return self.registry.register(
            ctx=self.ctx,
            tool_id=tool_id,
            manifest=ToolManifest(name="GitHub Search", tool_type=tool_type, required_connector_type="github"),
            permission=ToolPermission(
                required_rbac_scope="tools.execute",
                governance_approval_required=governance,
                allowed_output_classifications=("internal",),
            ),
        )

    def test_tool_registration_permission_and_connector_access_through_router(self) -> None:
        tool = self.register_tool()
        result, job = self.registry.execute(
            ctx=self.ctx,
            tool_id=tool.tool_id,
            payload={"connector_id": self.connector.connector_id, "data_class": "issues", "query_ref": "veil-query-ref"},
        )
        self.assertEqual(job.job_type, "tool_execution")
        self.assertTrue(result.persisted)
        self.assertIn("sanitized_payload", result.output)
        self.assertEqual(self.veil.policy_calls, 2)
        self.assertGreaterEqual(self.veil.sanitize_calls, 2)
        self.assertTrue(any(event.event_type == "tool.executed" for event in self.events.replay()))

    def test_permission_veil_governance_tenant_and_raw_rejections(self) -> None:
        tool = self.register_tool(governance=True)
        with self.assertRaises(AuthorizationError):
            self.registry.execute(
                ctx=self.ctx,
                tool_id=tool.tool_id,
                payload={"connector_id": self.connector.connector_id, "data_class": "issues", "query_ref": "veil-query-ref"},
            )
        approved, _job = self.registry.execute(
            ctx=self.ctx,
            tool_id=tool.tool_id,
            payload={"connector_id": self.connector.connector_id, "data_class": "issues", "query_ref": "veil-query-ref"},
            governance_approved=True,
        )
        self.assertEqual(approved.classification, "internal")

        missing_scope = TenantContext("tenant-a", "org-a", "viewer-a", ("tools.read",))
        with self.assertRaises(AuthorizationError):
            self.registry.execute(ctx=missing_scope, tool_id=tool.tool_id, payload={"connector_id": self.connector.connector_id})

        other_tenant = TenantContext("tenant-b", "org-b", "owner-b", ("tools.execute",))
        with self.assertRaises(AuthorizationError):
            self.registry.get(other_tenant, tool.tool_id)

        with self.assertRaises(ValidationError):
            self.registry.execute(ctx=self.ctx, tool_id=tool.tool_id, payload={"raw": "secret"}, governance_approved=True)

        denied_registry = ToolRegistry(
            persistence=self.store,
            event_store=self.events,
            veil_client=DenyVeilClient(),
            router=ToolRouter(connector_registry=self.connector_registry),
            runtime=self.runtime,
        )
        with self.assertRaises(AuthorizationError):
            denied_registry.execute(
                ctx=self.ctx,
                tool_id=tool.tool_id,
                payload={"connector_id": self.connector.connector_id, "data_class": "issues", "query_ref": "veil-query-ref"},
                governance_approved=True,
            )

    def test_sanitized_intelligence_workflow_metering_and_audit_bundle(self) -> None:
        tool = self.register_tool(tool_id="tool-ticket-analysis", tool_type="ticket_analysis")
        graph = TaskGraph(
            graph_id="wf-tool",
            nodes=(TaskNode(node_id="analyze", agent_id="analysis-agent", capability="analysis"),),
        )

        def runner(_node, _payload):
            result, _job = self.registry.execute(
                ctx=self.ctx,
                tool_id=tool.tool_id,
                payload={"sanitized_payload": {"ticket": "sanitized"}, "veil_token_refs": ("veil-ticket-ref",)},
            )
            self.store.put("usage_events", "tool-meter", {"tenant_id": "tenant-a", "event_type": "tool_executions", "quantity": 1, "metadata": {}, "usage_id": "tool-meter", "timestamp": result.created_at.isoformat()})
            return result.as_dict()

        state = MeshWorkflowEngine(context_store=ContextStore(), event_store=self.events).start(
            task_graph=graph,
            initial_payload={"tenant_id": "tenant-a", "organization_id": "org-a"},
            node_runner=runner,
        )
        self.assertEqual(state["status"], "completed")
        bundle = AuditBundleExporter(persistence=self.store, event_store=self.events).export("tenant-a").as_dict()
        self.assertEqual(bundle["tools"][0]["tool_id"], tool.tool_id)
        self.assertTrue(bundle["tool_results"])
        self.assertFalse(contains_raw_sensitive(bundle))

    def test_seed_tool_packages_exist(self) -> None:
        seed = json.loads((Path(__file__).resolve().parents[1] / "examples/tools/seed_tools.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {item["tool_id"] for item in seed},
            {
                "tool-gmail-search",
                "tool-m365-document-search",
                "tool-jira-ticket-analysis",
                "tool-servicenow-incident-summary",
                "tool-github-repository-review",
                "tool-audit-bundle-export",
            },
        )


class Generation13ToolApiTests(unittest.TestCase):
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
        self.client.post(
            "/connectors",
            json={
                "connector_id": "connector-github",
                "connector_type": "github",
                "display_name": "GitHub",
                "data_classes": ["issues"],
                "credentials": {"credential_ref": "veil-credential-ref:github", "provider": "github"},
                "policy": {"allowed_data_classes": ["issues"]},
            },
            headers=self.headers,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_tool_api_registration_execute_health_execution_lookup_and_metering(self) -> None:
        created = self.client.post(
            "/tools",
            json={
                "tool_id": "tool-github-search",
                "name": "GitHub Search",
                "tool_type": "connector_search",
                "required_connector_type": "github",
                "permission": {"required_rbac_scope": "tools.execute", "allowed_output_classifications": ["internal"]},
            },
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(self.client.get("/tools", headers=self.headers).json()["total"], 1)
        self.assertEqual(self.client.get("/tools/tool-github-search/health", headers=self.headers).json()["status"], "active")

        executed = self.client.post(
            "/tools/tool-github-search/execute",
            json={"payload": {"connector_id": "connector-github", "data_class": "issues", "query_ref": "veil-query-ref"}},
            headers=self.headers,
        )
        self.assertEqual(executed.status_code, 200)
        body = executed.json()
        self.assertEqual(body["job"]["job_type"], "tool_execution")
        execution_id = body["result"]["execution_id"]
        self.assertEqual(self.client.get(f"/tools/executions/{execution_id}", headers=self.headers).status_code, 200)
        usage = self.client.get("/tenants/tenant-a/usage", headers=self.headers).json()
        self.assertGreaterEqual(usage["usage"].get("tool_executions", 0), 1)

        raw = self.client.post(
            "/tools/tool-github-search/execute",
            json={"payload": {"raw": "secret"}},
            headers=self.headers,
        )
        self.assertEqual(raw.status_code, 400)
        self.assertEqual(self.client.get("/tools").status_code, 401)


if __name__ == "__main__":
    unittest.main()
