from __future__ import annotations

from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agent_observability import (
    AgentMetric,
    AnomalyDetector,
    HealthEngine,
    OperationalIntelligenceService,
    TrendAnalyzer,
    VersionComparator,
)
from agentfabric.audit_bundle import AuditBundleExporter
from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError
from agentfabric.events import EventStore
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings


class Generation16ObservabilityServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryPersistenceStore()
        self.events = EventStore(persistence=self.store)
        self.service = OperationalIntelligenceService(self.store, self.events)
        self.ctx = TenantContext("tenant-a", "org-a", "owner-a", ())

    def metric(self, name: str, value: float, *, version: str = "1.0.0", offset: int = 0) -> AgentMetric:
        return AgentMetric(
            tenant_id="tenant-a",
            agent_id="agent-a",
            version=version,
            metric=name,
            value=value,
            timestamp=datetime.now(tz=timezone.utc) + timedelta(seconds=offset),
        )

    def test_metric_recording_aggregation_health_states_and_trends(self) -> None:
        healthy = HealthEngine().compute(
            "tenant-a",
            "agent-a",
            "1.0.0",
            [
                self.metric("evaluation_score", 0.95),
                self.metric("latency", 500),
                self.metric("reliability", 0.98),
                self.metric("cost", 0.2),
                self.metric("user_rating", 4.8),
            ],
        )
        warning = HealthEngine().compute(
            "tenant-a",
            "agent-a",
            "1.0.0",
            [self.metric("evaluation_score", 0.75), self.metric("latency", 1800)],
        )
        degraded = HealthEngine().compute(
            "tenant-a",
            "agent-a",
            "1.0.0",
            [self.metric("evaluation_score", 0.55), self.metric("latency", 4000)],
        )
        critical = HealthEngine().compute(
            "tenant-a",
            "agent-a",
            "1.0.0",
            [self.metric("evaluation_score", 0.2), self.metric("hallucination_rate", 0.9), self.metric("latency", 9000)],
        )
        self.assertEqual([healthy.status, warning.status, degraded.status, critical.status], ["healthy", "warning", "degraded", "critical"])

        self.service.record_metric(self.metric("latency", 100))
        self.service.record_metric(self.metric("latency", 200, offset=1))
        aggregate = self.service.aggregate(self.ctx, agent_id="agent-a")
        self.assertEqual(aggregate["metrics"]["latency"]["average"], 150.0)
        trend = TrendAnalyzer().analyze(self.service.list_metrics(self.ctx, agent_id="agent-a"), period="hourly")
        self.assertEqual(trend["p50"], 100)
        self.assertEqual(len(trend["rolling_average"]), 2)

    def test_drift_anomaly_recommendation_events_and_audit_reproducibility(self) -> None:
        for index, value in enumerate([0.95, 0.94, 0.96, 0.4]):
            self.service.record_metric(self.metric("evaluation_score", value, offset=index))
        for index, value in enumerate([100, 105, 95, 1200]):
            self.service.record_metric(self.metric("latency", value, offset=10 + index))

        drift = self.service.list_drift(self.ctx, "agent-a")
        anomalies = self.service.list_anomalies(self.ctx, "agent-a")
        recommendations = self.service.list_recommendations(self.ctx, "agent-a")
        self.assertTrue(any(item.metric == "evaluation_score" for item in drift))
        self.assertTrue(any(item.metric == "latency" for item in anomalies))
        self.assertGreater(recommendations[-1].confidence, 0.5)

        event_types = {event.event_type for event in self.events.replay()}
        self.assertIn("agent.metric.recorded", event_types)
        self.assertIn("agent.drift.detected", event_types)
        self.assertIn("agent.anomaly.detected", event_types)
        self.assertIn("agent.recommendation.created", event_types)

        bundle = AuditBundleExporter(persistence=self.store, event_store=self.events).export("tenant-a").as_dict()
        self.assertTrue(bundle["health_snapshots"])
        self.assertTrue(bundle["drift_events"])
        self.assertTrue(bundle["anomaly_events"])
        self.assertTrue(bundle["recommendations"])
        self.assertTrue(bundle["event_hash_chain"]["valid"])

    def test_version_comparison_better_same_worse_and_tenant_isolation(self) -> None:
        metrics = [
            self.metric("evaluation_score", 0.7, version="1.0.0"),
            self.metric("latency", 1000, version="1.0.0"),
            self.metric("cost", 1.0, version="1.0.0"),
            self.metric("evaluation_score", 0.9, version="1.1.0"),
            self.metric("latency", 700, version="1.1.0"),
            self.metric("cost", 0.8, version="1.1.0"),
            self.metric("evaluation_score", 0.7, version="1.0.1"),
            self.metric("latency", 1000, version="1.0.1"),
            self.metric("cost", 1.0, version="1.0.1"),
            self.metric("evaluation_score", 0.4, version="0.9.0"),
            self.metric("latency", 1800, version="0.9.0"),
            self.metric("cost", 2.0, version="0.9.0"),
        ]
        comparator = VersionComparator()
        self.assertEqual(comparator.compare(tenant_id="tenant-a", agent_id="agent-a", baseline_version="1.0.0", candidate_version="1.1.0", metrics=metrics).result, "better")
        self.assertEqual(comparator.compare(tenant_id="tenant-a", agent_id="agent-a", baseline_version="1.0.0", candidate_version="1.0.1", metrics=metrics).result, "same")
        self.assertEqual(comparator.compare(tenant_id="tenant-a", agent_id="agent-a", baseline_version="1.0.0", candidate_version="0.9.0", metrics=metrics).result, "worse")

        for metric in metrics:
            self.service.record_metric(metric)
        other = TenantContext("tenant-b", "org-b", "owner-b", ())
        self.assertEqual(self.service.list_metrics(other, agent_id="agent-a"), [])
        with self.assertRaises(AuthorizationError):
            recommendation = self.service.list_recommendations(self.ctx, "agent-a")[-1]
            self.service.approve_recommendation(other, "agent-a", recommendation.recommendation_id)

    def test_marketplace_gate_fails_closed_on_degraded_quality(self) -> None:
        for name, value in [
            ("evaluation_score", 0.3),
            ("hallucination_rate", 0.8),
            ("latency", 9000),
            ("user_rating", 1.0),
            ("correction_frequency", 1.0),
        ]:
            self.service.record_metric(self.metric(name, value))
        with self.assertRaises(AuthorizationError):
            self.service.enforce_marketplace_gate(self.ctx, "agent-a", "1.0.0")

    def test_anomaly_outlier_handling(self) -> None:
        stable = [self.metric("latency", value, offset=index) for index, value in enumerate([100, 102, 98, 101])]
        self.assertEqual(AnomalyDetector().detect(stable), [])
        spike = stable + [self.metric("latency", 1000, offset=5)]
        self.assertEqual(AnomalyDetector().detect(spike)[0].metric, "latency")


class Generation16ObservabilityApiTests(unittest.TestCase):
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

    def record(self, metric: str, value: float, version: str = "1.0.0") -> None:
        response = self.client.post(
            "/observability/metrics",
            json={"agent_id": "agent-api", "version": version, "metric": metric, "value": value},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)

    def test_api_rbac_comparison_recommendation_and_marketplace_gate(self) -> None:
        self.assertEqual(self.client.get("/observability/metrics").status_code, 401)
        for version, score, latency, cost in [
            ("1.0.0", 0.9, 500, 0.5),
            ("1.1.0", 0.95, 400, 0.4),
        ]:
            self.record("evaluation_score", score, version)
            self.record("latency", latency, version)
            self.record("cost", cost, version)
        metrics = self.client.get("/observability/metrics?agent_id=agent-api", headers=self.headers)
        self.assertEqual(metrics.status_code, 200)
        self.assertEqual(metrics.json()["total"], 6)
        self.assertEqual(self.client.get("/agents/agent-api/health", headers=self.headers).status_code, 200)
        comparison = self.client.post(
            "/agents/agent-api/compare",
            json={"baseline_version": "1.0.0", "candidate_version": "1.1.0"},
            headers=self.headers,
        )
        self.assertEqual(comparison.status_code, 200)
        self.assertEqual(comparison.json()["result"], "better")
        recommendations = self.client.get("/agents/agent-api/recommendations", headers=self.headers).json()["items"]
        approved = self.client.post(
            f"/agents/agent-api/recommendations/{recommendations[-1]['recommendation_id']}/approve",
            headers=self.headers,
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "approved")

        for name, value in [
            ("evaluation_score", 0.2),
            ("hallucination_rate", 0.9),
            ("latency", 9000),
            ("user_rating", 1.0),
            ("correction_frequency", 1.0),
        ]:
            self.record(name, value, "2.0.0")
        blocked = self.client.post(
            "/marketplace/packages",
            json={
                "package_id": "pkg-degraded",
                "name": "Degraded",
                "version": "2.0.0",
                "agent_identity_id": "agent-api",
            },
            headers=self.headers,
        )
        self.assertEqual(blocked.status_code, 403)


if __name__ == "__main__":
    unittest.main()
