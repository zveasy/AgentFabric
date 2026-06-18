from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.enterprise import Membership, MembershipService, TenantContext, TenantIsolation, TenantService
from agentfabric.errors import AuthorizationError, ConflictError
from agentfabric.events import EventStore
from agentfabric.metering import MeteringService
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.quotas import LimitEnforcer, QuotaPolicy, QuotaTracker
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings
from agentfabric.server.payments import get_billing_plan
from veil_client import MockVeilClient


class Generation5ServiceTests(unittest.TestCase):
    def test_tenant_persistence_and_isolation(self) -> None:
        store = MemoryPersistenceStore()
        tenants = TenantService(store)
        tenant = tenants.create_tenant(
            tenant_id="tenant-a",
            organization_id="org-a",
            name="Tenant A",
            created_by="owner",
        )
        store.put("workflows", "wf-a", {"tenant_id": "tenant-a", "organization_id": "org-a"})
        store.put("workflows", "wf-b", {"tenant_id": "tenant-b", "organization_id": "org-b"})

        self.assertEqual(tenant.organization_id, "org-a")
        self.assertEqual(len(store.list_tenant("workflows", "tenant-a")), 1)

        isolation = TenantIsolation()
        ctx = TenantContext(tenant_id="tenant-a", organization_id="org-a", principal_id="owner")
        isolation.assert_tenant(ctx, {"tenant_id": "tenant-a"})
        with self.assertRaises(AuthorizationError):
            isolation.assert_tenant(ctx, {"tenant_id": "tenant-b"})
        with self.assertRaises(AuthorizationError):
            isolation.require_context(None)

    def test_membership_service_account_restriction(self) -> None:
        store = MemoryPersistenceStore()
        memberships = MembershipService(store)
        with self.assertRaises(PermissionError):
            memberships.add(
                Membership(
                    principal_id="target",
                    tenant_id="tenant-a",
                    organization_id="org-a",
                    role="admin",
                    member_type="user",
                    created_by="svc",
                ),
                actor_member_type="service_account",
                actor_role="admin",
            )

    def test_quota_enforcement_and_metering_reconstruction(self) -> None:
        tracker = QuotaTracker()
        enforcer = LimitEnforcer(tracker)
        policy = QuotaPolicy(workflow_runs_per_day=1)
        enforcer.consume("tenant-a", policy, "workflow_runs_per_day")
        with self.assertRaises(ConflictError):
            enforcer.consume("tenant-a", policy, "workflow_runs_per_day")

        store = MemoryPersistenceStore()
        metering = MeteringService(store)
        metering.record("tenant-a", "workflow_runs")
        self.assertEqual(metering.aggregate("tenant-a"), {"workflow_runs": 1})

        events = EventStore()
        events.append("workflow.started", "wf", {"tenant_id": "tenant-a"})
        events.append("task.completed", "wf", {"tenant_id": "tenant-a", "agent_id": "agent", "node_id": "n"})
        self.assertEqual(
            metering.reconstruct_from_events("tenant-a", events),
            {"workflow_runs": 1, "task_executions": 1},
        )

    def test_billing_plans_define_commercial_controls(self) -> None:
        dev = get_billing_plan("dev")
        enterprise = get_billing_plan("enterprise")
        self.assertLess(dev.max_agents, enterprise.max_agents)
        self.assertIn("publish", enterprise.marketplace_permissions)

    def test_veil_boundary_remains_external(self) -> None:
        veil = MockVeilClient()
        policy = veil.check_policy(type("Req", (), {"agent_id": "a", "action": "x", "payload": {}})())
        self.assertTrue(policy.allowed)


class Generation5ApiTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_tenant_team_membership_usage_quota_billing_and_audit_apis(self) -> None:
        tenant = self.client.post(
            "/tenants",
            json={"tenant_id": "tenant-a", "organization_id": "org-a", "name": "Tenant A", "billing_plan": "team"},
            headers=self.headers,
        )
        self.assertEqual(tenant.status_code, 200)

        team = self.client.post("/tenants/tenant-a/teams", json={"name": "Platform"}, headers=self.headers)
        self.assertEqual(team.status_code, 200)
        self.assertEqual(self.client.get("/tenants/tenant-a/teams", headers=self.headers).json()["total"], 1)

        member = self.client.post(
            "/tenants/tenant-a/members",
            json={"principal_id": "dev-a", "role": "developer", "member_type": "user"},
            headers=self.headers,
        )
        self.assertEqual(member.status_code, 200)
        self.assertEqual(self.client.get("/tenants/tenant-a/members", headers=self.headers).json()["total"], 2)

        quotas = self.client.get("/tenants/tenant-a/quotas", headers=self.headers)
        self.assertEqual(quotas.status_code, 200)
        patched = self.client.patch("/tenants/tenant-a/quotas", json={"workflow_runs_per_day": 1}, headers=self.headers)
        self.assertEqual(patched.json()["limits"]["workflow_runs_per_day"], 1)

        first = self.client.post(
            "/workflow/start",
            json={"workflow_id": "tenant-wf-1", "nodes": [{"node_id": "research", "capability": "research"}]},
            headers=self.headers,
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            "/workflow/start",
            json={"workflow_id": "tenant-wf-2", "nodes": [{"node_id": "research", "capability": "research"}]},
            headers=self.headers,
        )
        self.assertEqual(second.status_code, 409)

        usage = self.client.get("/tenants/tenant-a/usage", headers=self.headers)
        self.assertEqual(usage.status_code, 200)
        self.assertGreaterEqual(usage.json()["usage"]["workflow_runs"], 1)

        billing = self.client.get("/tenants/tenant-a/billing", headers=self.headers)
        self.assertEqual(billing.json()["plan"]["plan_id"], "team")
        updated_billing = self.client.patch(
            "/tenants/tenant-a/billing",
            json={"billing_plan": "enterprise"},
            headers=self.headers,
        )
        self.assertEqual(updated_billing.json()["plan"]["plan_id"], "enterprise")

        audit = self.client.get("/tenants/tenant-a/audit-export", headers=self.headers)
        self.assertEqual(audit.status_code, 200)
        self.assertTrue(all(event["payload"].get("tenant_id") == "tenant-a" for event in audit.json()["events"]))

    def test_tenant_aware_memory_events_reputation_and_cross_tenant_rejection(self) -> None:
        self.client.post(
            "/tenants",
            json={"tenant_id": "tenant-a", "organization_id": "org-a", "name": "Tenant A"},
            headers=self.headers,
        )
        workflow = self.client.post(
            "/workflow/start",
            json={"workflow_id": "tenant-aware-wf", "nodes": [{"node_id": "research", "capability": "research"}]},
            headers=self.headers,
        )
        self.assertEqual(workflow.status_code, 200)

        events = self.client.get("/events", headers=self.headers)
        self.assertGreater(events.json()["total"], 0)
        self.assertTrue(all(item["payload"].get("tenant_id") == "tenant-a" for item in events.json()["items"]))

        memory = self.client.post(
            "/memory/research-agent",
            json={"content": {"summary": "tenant safe"}, "source_workflow_id": "tenant-aware-wf"},
            headers=self.headers,
        )
        self.assertEqual(memory.status_code, 200)
        listed = self.client.get("/memory/research-agent", headers=self.headers)
        self.assertEqual(listed.json()["total"], 1)

        reputation = self.client.get("/agents/research-agent/reputation", headers=self.headers)
        self.assertEqual(reputation.status_code, 200)
        self.assertGreaterEqual(reputation.json()["successful_tasks"], 1)

        cross = self.client.get("/tenants/tenant-b/usage", headers=self.headers)
        self.assertEqual(cross.status_code, 403)

    def test_api_auth_and_quota_fail_closed(self) -> None:
        self.assertEqual(self.client.get("/tenants").status_code, 401)
        self.client.post(
            "/tenants",
            json={"tenant_id": "tenant-a", "organization_id": "org-a", "name": "Tenant A"},
            headers=self.headers,
        )
        self.client.patch("/tenants/tenant-a/quotas", json={"memory_records": 0}, headers=self.headers)
        blocked = self.client.post(
            "/memory/research-agent",
            json={"content": {"summary": "blocked"}},
            headers=self.headers,
        )
        self.assertEqual(blocked.status_code, 409)


if __name__ == "__main__":
    unittest.main()
