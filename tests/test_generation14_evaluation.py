from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.audit_bundle import AuditBundleExporter, contains_raw_sensitive
from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError
from agentfabric.evaluation import EvaluationCase, EvaluationDataset, EvaluationRunner, QualityGateService
from agentfabric.feedback import FeedbackService
from agentfabric.events import EventStore
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.reputation import ReputationService
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings
from veil_client import AuditEventResponse, MockVeilClient, PolicyCheckResponse


class SpyVeilClient(MockVeilClient):
    def __init__(self) -> None:
        self.policy_calls = 0
        self.audit_calls = 0

    def check_policy(self, request):
        self.policy_calls += 1
        return PolicyCheckResponse(allowed=True)

    def create_audit_event(self, request):
        self.audit_calls += 1
        return AuditEventResponse(event_id=f"audit:{request.event_type}", accepted=True)


class DenyVeilClient(SpyVeilClient):
    def check_policy(self, request):
        self.policy_calls += 1
        return PolicyCheckResponse(allowed=False, reason="evaluation denied")


class Generation14EvaluationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryPersistenceStore()
        self.events = EventStore(persistence=self.store)
        self.veil = SpyVeilClient()
        self.reputation = ReputationService(persistence=self.store)
        self.runner = EvaluationRunner(
            persistence=self.store,
            event_store=self.events,
            veil_client=self.veil,
            reputation=self.reputation,
        )
        self.ctx = TenantContext(
            tenant_id="tenant-a",
            organization_id="org-a",
            principal_id="owner-a",
            roles=("evaluations.read", "evaluations.manage", "feedback.read", "feedback.write"),
        )

    def dataset(self) -> EvaluationDataset:
        return EvaluationDataset(
            dataset_id="eval-dataset-doc",
            tenant_id="tenant-a",
            organization_id="org-a",
            name="Document Summary",
            created_by="owner-a",
            cases=(
                EvaluationCase(
                    case_id="case-1",
                    input_ref="veil-doc-ref",
                    target_type="agent_output",
                    target_id="agent-a",
                    expected_output={"summary": "present", "classification": "internal"},
                ),
            ),
        )

    def test_evaluation_dataset_run_scorecard_gate_and_reputation(self) -> None:
        dataset = self.runner.create_dataset(self.dataset())
        result = self.runner.run(
            ctx=self.ctx,
            dataset_id=dataset.dataset_id,
            target_type="agent_output",
            target_id="agent-a",
            outputs=[{"summary": "safe", "classification": "internal"}],
        )
        self.assertGreaterEqual(result.overall_score, 0.8)
        scorecard = self.runner.scorecard(self.ctx, result.run_id)
        self.assertTrue(scorecard.passed)
        QualityGateService().enforce("agent_runtime_execution", scorecard)
        self.assertGreater(self.reputation.get("agent-a", tenant_id="tenant-a").average_human_rating, 0)
        self.assertEqual(self.veil.policy_calls, 1)
        self.assertEqual(self.veil.audit_calls, 1)

    def test_quality_gate_fail_veil_denial_tenant_isolation_and_raw_dataset_rejection(self) -> None:
        dataset = self.runner.create_dataset(self.dataset())
        failed = self.runner.run(
            ctx=self.ctx,
            dataset_id=dataset.dataset_id,
            target_type="marketplace_package",
            target_id="package-a",
            outputs=[{"unrelated": "value"}],
        )
        with self.assertRaises(AuthorizationError):
            QualityGateService().enforce("package_publish", self.runner.scorecard(self.ctx, failed.run_id))

        other_ctx = TenantContext("tenant-b", "org-b", "owner-b", ("evaluations.read",))
        with self.assertRaises(AuthorizationError):
            self.runner.get_result(other_ctx, failed.run_id)

        with self.assertRaises(ValueError):
            self.runner.create_dataset(
                EvaluationDataset(
                    tenant_id="tenant-a",
                    organization_id="org-a",
                    name="Unsafe",
                    created_by="owner-a",
                    cases=(EvaluationCase("unsafe", "veil-ref", expected_output={"raw": "secret"}),),
                )
            )

        denied = EvaluationRunner(
            persistence=self.store,
            event_store=self.events,
            veil_client=DenyVeilClient(),
            reputation=self.reputation,
        )
        with self.assertRaises(AuthorizationError):
            denied.run(ctx=self.ctx, dataset_id=dataset.dataset_id, target_type="agent_output", target_id="agent-a", outputs=[{}])

    def test_feedback_correction_and_audit_bundle_inclusion(self) -> None:
        dataset = self.runner.create_dataset(self.dataset())
        result = self.runner.run(
            ctx=self.ctx,
            dataset_id=dataset.dataset_id,
            target_type="agent_output",
            target_id="agent-a",
            outputs=[{"summary": "safe", "classification": "internal"}],
        )
        feedback = FeedbackService(persistence=self.store, event_store=self.events, reputation=self.reputation)
        record = feedback.create(
            self.ctx,
            {
                "target_type": "agent",
                "target_id": "agent-a",
                "feedback_type": "human_rating",
                "rating": 4.5,
                "notes": "good pilot answer",
                "correction_notes": "include citations next time",
            },
        )
        self.assertTrue(record.correction_id)
        correction = feedback.get_correction(self.ctx, str(record.correction_id))
        self.assertIn("citations", correction.notes)
        bundle = AuditBundleExporter(persistence=self.store, event_store=self.events).export("tenant-a").as_dict()
        self.assertEqual(bundle["evaluation_results"][0]["run_id"], result.run_id)
        self.assertEqual(bundle["feedback"][0]["feedback_id"], record.feedback_id)
        self.assertFalse(contains_raw_sensitive(bundle))

    def test_sample_evaluation_datasets_exist(self) -> None:
        root = Path(__file__).resolve().parents[1] / "examples/evaluations"
        expected = {
            "document_summary.json",
            "email_analysis.json",
            "ticket_triage.json",
            "code_review.json",
            "governance_proposal_quality.json",
            "marketplace_risk_summary.json",
            "federated_delegation_response.json",
        }
        self.assertEqual(expected, {path.name for path in root.glob("*.json")})
        for filename in expected:
            payload = json.loads((root / filename).read_text(encoding="utf-8"))
            self.assertTrue(payload["cases"][0]["input_ref"].startswith("veil-"))


class Generation14EvaluationApiTests(unittest.TestCase):
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

    def create_dataset(self) -> str:
        response = self.client.post(
            "/evaluations/datasets",
            json={
                "dataset_id": "eval-dataset-api",
                "name": "API Evaluation",
                "cases": [
                    {
                        "case_id": "case-1",
                        "input_ref": "veil-input-ref",
                        "expected_output": {"summary": "present", "classification": "internal"},
                    }
                ],
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["dataset_id"]

    def test_evaluation_feedback_quality_and_marketplace_gate_api(self) -> None:
        dataset_id = self.create_dataset()
        self.assertEqual(self.client.get("/evaluations/datasets", headers=self.headers).json()["total"], 1)
        run = self.client.post(
            "/evaluations/run",
            json={
                "dataset_id": dataset_id,
                "target_type": "marketplace_package",
                "target_id": "pkg-low",
                "outputs": [{"unrelated": "value"}],
            },
            headers=self.headers,
        )
        self.assertEqual(run.status_code, 200)
        run_id = run.json()["run_id"]
        scorecard = self.client.get(f"/evaluations/runs/{run_id}/scorecard", headers=self.headers)
        self.assertEqual(scorecard.status_code, 200)
        self.assertFalse(scorecard.json()["passed"])
        self.assertEqual(self.client.get("/marketplace/packages/pkg-low/quality", headers=self.headers).json()["status"], "measured")

        blocked = self.client.post(
            "/marketplace/packages",
            json={
                "package_id": "pkg-low",
                "name": "Low Package",
                "version": "1.0.0",
                "agent_identity_id": "agent-low",
                "quality_gate_required": True,
            },
            headers=self.headers,
        )
        self.assertEqual(blocked.status_code, 403)

        agent_run = self.client.post(
            "/evaluations/run",
            json={
                "dataset_id": dataset_id,
                "target_type": "agent_output",
                "target_id": "agent-quality",
                "outputs": [{"summary": "safe", "classification": "internal"}],
            },
            headers=self.headers,
        )
        self.assertEqual(agent_run.status_code, 200)
        quality = self.client.get("/agents/agent-quality/quality", headers=self.headers)
        self.assertEqual(quality.json()["status"], "measured")

        feedback = self.client.post(
            "/feedback",
            json={
                "target_type": "agent",
                "target_id": "agent-quality",
                "feedback_type": "human_rating",
                "rating": 4,
                "notes": "accurate",
                "correction_notes": "add sources",
            },
            headers=self.headers,
        )
        self.assertEqual(feedback.status_code, 200)
        self.assertTrue(feedback.json()["correction_id"])
        self.assertEqual(self.client.get("/feedback", headers=self.headers).json()["total"], 1)
        self.assertEqual(self.client.get("/evaluations/run").status_code, 401)


if __name__ == "__main__":
    unittest.main()
