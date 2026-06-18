from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.audit_bundle import AuditBundleExporter
from agentfabric.cloud import CloudRuntime, RuntimeJob
from agentfabric.cloud.queue_backends import MemoryJobQueue
from agentfabric.economics import CostTracker, MarginAnalyzer, PackageRevenue, PricingPolicy, RevenueTracker, TenantProfitability
from agentfabric.errors import AuthorizationError
from agentfabric.events import EventStore
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings
from veil_client import MockVeilClient


class Generation15EconomicsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryPersistenceStore()
        self.events = EventStore(persistence=self.store)
        self.costs = CostTracker(self.store)
        self.revenue = RevenueTracker(self.store)

    def test_cost_revenue_profitability_package_revenue_pricing_and_audit_bundle(self) -> None:
        cost = self.costs.record("tenant-a", "tool_execution", source_id="tool-exec")
        revenue = self.revenue.record("tenant-a", "marketplace", amount=25.0, source_id="pkg-a", package_id="pkg-a")
        self.events.append("economics.cost.recorded", cost.event_id, cost.as_dict())
        self.events.append("economics.revenue.recorded", revenue.event_id, revenue.as_dict())

        self.assertGreater(self.costs.total("tenant-a"), 0)
        self.assertEqual(self.revenue.total("tenant-a"), 25.0)
        report = TenantProfitability(MarginAnalyzer(costs=self.costs, revenue=self.revenue)).report("tenant-a")
        self.assertGreater(report["profit"], 0)
        self.assertGreater(report["gross_margin"], 0)
        self.assertEqual(PackageRevenue(self.store).report("pkg-a", "tenant-a")["revenue"], 25.0)
        self.assertEqual(PricingPolicy(per_seat=10, per_tool_call=1).calculate({"seats": 2, "tool_calls": 3}), 23.0)

        bundle = AuditBundleExporter(persistence=self.store, event_store=self.events).export("tenant-a").as_dict()
        self.assertEqual(bundle["cost_events"][0]["event_id"], cost.event_id)
        self.assertEqual(bundle["revenue_events"][0]["event_id"], revenue.event_id)

    def test_spend_limit_enforcement_and_runtime_job_block(self) -> None:
        self.costs.set_spend_limits("tenant-a", {"tenant_spend_limit": 0.0})
        with self.assertRaises(AuthorizationError):
            self.costs.enforce("tenant-a", "agent_run")

        runtime = CloudRuntime(
            queue=MemoryJobQueue(),
            persistence=self.store,
            event_store=self.events,
            veil_client=MockVeilClient(),
        )
        runtime.dispatcher.spend_check = lambda job: self.costs.enforce(job.tenant_id, "agent_run", source_id=job.job_id)
        job = runtime.submit(
            RuntimeJob(
                tenant_id="tenant-a",
                organization_id="org-a",
                created_by="owner-a",
                job_type="agent_run",
                payload={"agent_id": "agent-a"},
            )
        )
        with self.assertRaises(AuthorizationError):
            runtime.dispatcher.execute(job)

    def test_tenant_isolation_for_cost_and_revenue_lists(self) -> None:
        self.costs.record("tenant-a", "agent_run")
        self.costs.record("tenant-b", "agent_run")
        self.revenue.record("tenant-a", "subscription", amount=100.0)
        self.revenue.record("tenant-b", "subscription", amount=200.0)
        self.assertEqual(len(self.costs.list_for_tenant("tenant-a")), 1)
        self.assertEqual(self.revenue.total("tenant-a"), 100.0)


class Generation15EconomicsApiTests(unittest.TestCase):
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
        tenant = self.client.post(
            "/tenants",
            json={"tenant_id": "tenant-a", "organization_id": "org-a", "name": "Tenant A", "billing_plan": "enterprise"},
            headers=self.headers,
        )
        self.assertEqual(tenant.status_code, 200)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_economics_apis_billing_plan_revenue_runtime_costs_package_revenue_and_spend_cap(self) -> None:
        revenue = self.client.get("/economics/tenants/tenant-a/revenue", headers=self.headers)
        self.assertEqual(revenue.status_code, 200)
        self.assertGreaterEqual(revenue.json()["total_revenue"], 5000.0)

        job = self.client.post(
            "/runtime/jobs",
            json={"job_type": "workflow_step", "payload": {"agent_id": "agent-a"}},
            headers=self.headers,
        )
        self.assertEqual(job.status_code, 200)
        costs = self.client.get("/economics/tenants/tenant-a/costs", headers=self.headers)
        self.assertGreater(costs.json()["total_cost"], 0)
        runtime_costs = self.client.get("/economics/runtime/costs", headers=self.headers)
        self.assertGreater(runtime_costs.json()["total_cost"], 0)
        margin = self.client.get("/economics/tenants/tenant-a/margin", headers=self.headers)
        self.assertIn("gross_margin", margin.json())
        summary = self.client.get("/economics/tenants/tenant-a", headers=self.headers)
        self.assertIn("profit", summary.json())

        publish = self.client.post(
            "/marketplace/packages",
            json={"package_id": "pkg-revenue", "name": "Pkg Revenue", "version": "1.0.0", "agent_identity_id": "agent-pkg"},
            headers=self.headers,
        )
        self.assertEqual(publish.status_code, 200)
        package_revenue = self.client.get("/economics/packages/pkg-revenue/revenue", headers=self.headers)
        self.assertGreater(package_revenue.json()["revenue"], 0)

        limits = self.client.patch(
            "/economics/tenants/tenant-a/spend-limits",
            json={"tenant_spend_limit": 0.0},
            headers=self.headers,
        )
        self.assertEqual(limits.status_code, 200)
        blocked = self.client.post(
            "/runtime/jobs",
            json={"job_type": "agent_run", "payload": {"agent_id": "agent-a"}, "dispatch_now": True},
            headers=self.headers,
        )
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(self.client.get("/economics/tenants/tenant-a/costs").status_code, 401)


if __name__ == "__main__":
    unittest.main()
