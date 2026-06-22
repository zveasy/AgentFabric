from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.audit_bundle import AuditBundleExporter
from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError
from agentfabric.events import EventStore
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.repository_execution import RepositoryExecutionEngine, validate_relative_path
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings


PLATFORM_ROOT = Path(__file__).resolve().parents[1] / "platforms" / "renovation_os"


class Generation18RepositoryExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.output_root = Path(self.tmp.name) / "generated"
        self.store = MemoryPersistenceStore()
        self.events = EventStore(persistence=self.store)
        self.engine = RepositoryExecutionEngine(
            persistence=self.store,
            event_store=self.events,
            output_root=self.output_root,
            platform_root=PLATFORM_ROOT,
        )
        self.ctx = TenantContext("tenant-a", "org-a", "owner-a", ())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_plan_dry_run_approval_materialization_and_rollback(self) -> None:
        plan = self.engine.plan(self.ctx, "reno_estimator")
        self.assertTrue(all(plan.quality_gates.values()))
        repository_root = self.output_root / "tenant-a" / "reno_estimator"
        self.assertFalse(repository_root.exists())
        dry_run = self.engine.dry_run(self.ctx, plan.execution_id)
        self.assertEqual(dry_run.status, "dry_run_complete")
        self.assertFalse(repository_root.exists())

        with self.assertRaises(AuthorizationError):
            self.engine.execute(self.ctx, plan.execution_id)
        approval = self.engine.approve(self.ctx, plan.execution_id)
        self.assertEqual(approval.plan_digest, plan.digest)
        result = self.engine.execute(self.ctx, plan.execution_id)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.artifact_hashes, plan.artifact_hashes)
        self.assertTrue((repository_root / "README.md").is_file())
        models = (repository_root / "src/reno_estimator/models.py").read_text(encoding="utf-8")
        self.assertIn("class ProjectIntake", models)
        self.assertIn("class RiskAdjustment", models)
        self.assertTrue(result.marketplace_metadata["private"])

        rollback = self.engine.rollback(self.ctx, plan.execution_id)
        self.assertEqual(rollback["status"], "rolled_back")
        self.assertFalse(repository_root.exists())

    def test_three_renovation_repositories_and_deterministic_replay(self) -> None:
        expected_models = {
            "reno_estimator": "EstimateResult",
            "change_order_agent": "ChangeOrderAuditRecord",
            "contractor_command_center": "PaymentMilestone",
        }
        for repository_name, model in expected_models.items():
            plan = self.engine.plan(self.ctx, repository_name)
            replay = self.engine.replay(self.ctx, plan.execution_id)
            self.assertEqual(replay.execution_id, plan.execution_id)
            self.assertEqual(replay.artifact_hashes, plan.artifact_hashes)
            self.assertIn(model, plan.artifact_contents[f"src/{repository_name}/models.py"])
            self.assertIn("docs/architecture.md", plan.artifact_hashes)
            self.assertIn("openapi.json", plan.artifact_hashes)
            self.assertIn(".github/workflows/ci.yml", plan.artifact_hashes)
            reference_root = PLATFORM_ROOT / "repositories" / repository_name
            reference = {
                path.relative_to(reference_root).as_posix(): path.read_text(encoding="utf-8")
                for path in reference_root.rglob("*")
                if path.is_file() and path.suffix != ".pyc"
            }
            self.assertTrue(set(plan.artifact_contents) <= set(reference))
            self.assertIn("docs/product_logic.md", reference)

    def test_path_safety_tenant_isolation_events_and_audit(self) -> None:
        with self.assertRaises(ValueError):
            validate_relative_path("../outside")
        with self.assertRaises(ValueError):
            validate_relative_path("/absolute")
        plan = self.engine.plan(self.ctx, "change_order_agent")
        other = TenantContext("tenant-b", "org-b", "owner-b", ())
        with self.assertRaises(AuthorizationError):
            self.engine.get(other, plan.execution_id)
        self.engine.dry_run(self.ctx, plan.execution_id)
        self.engine.approve(self.ctx, plan.execution_id)
        self.engine.execute(self.ctx, plan.execution_id)
        event_types = {item["event_type"] for item in self.engine.events(self.ctx, plan.execution_id)}
        self.assertIn("factory.execution.planned", event_types)
        self.assertIn("factory.execution.step.completed", event_types)
        self.assertIn("factory.execution.completed", event_types)
        bundle = AuditBundleExporter(persistence=self.store, event_store=self.events).export("tenant-a").as_dict()
        self.assertTrue(bundle["factory_execution_plans"])
        self.assertNotIn("artifact_contents", bundle["factory_execution_plans"][0])
        self.assertTrue(bundle["factory_execution_approvals"])
        self.assertTrue(bundle["factory_execution_artifacts"])
        self.assertTrue(bundle["event_hash_chain"]["valid"])

    def test_divergent_existing_artifact_fails_closed(self) -> None:
        destination = self.output_root / "tenant-a" / "reno_estimator"
        conflict = destination / ".github" / "workflows" / "ci.yml"
        conflict.parent.mkdir(parents=True)
        conflict.write_text("unapproved content\n", encoding="utf-8")
        plan = self.engine.plan(self.ctx, "reno_estimator")
        self.engine.approve(self.ctx, plan.execution_id)
        with self.assertRaises(FileExistsError):
            self.engine.execute(self.ctx, plan.execution_id)
        self.assertEqual(conflict.read_text(encoding="utf-8"), "unapproved content\n")
        self.assertFalse((destination / "README.md").exists())


class Generation18RepositoryExecutionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.output_root = Path(self.tmp.name) / "api-generated"
        self.client = TestClient(
            create_app(
                Settings(
                    database_url=f"sqlite:///{Path(self.tmp.name) / 'api.db'}",
                    jwt_secret="test-secret",
                    bootstrap_token="bootstrap-test-token",
                    cloud_queue_backend="memory",
                    rate_limit_auth_per_minute=1000,
                    factory_output_root=str(self.output_root),
                )
            )
        )
        self.headers = self._principal("owner-a", "tenant-a", "owner")
        response = self.client.post(
            "/tenants",
            json={
                "tenant_id": "tenant-a",
                "organization_id": "org-a",
                "name": "Tenant A",
                "billing_plan": "enterprise",
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _principal(self, principal_id: str, tenant_id: str, role: str) -> dict[str, str]:
        headers = self.headers if hasattr(self, "headers") else {
            "X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"
        }
        self.client.post(
            "/auth/principals/register",
            json={"principal_id": principal_id, "tenant_id": tenant_id, "role": role, "scopes": []},
            headers=headers,
        )
        token = self.client.post(
            "/auth/token/issue",
            json={"principal_id": principal_id},
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        return {"Authorization": f"Bearer {token.json()['access_token']}"}

    def test_execution_api_approval_gate_artifacts_and_events(self) -> None:
        self.assertEqual(self.client.post("/factory/execution/plan", json={}).status_code, 401)
        planned = self.client.post(
            "/factory/execution/plan",
            json={"repository_id": "contractor_command_center"},
            headers=self.headers,
        )
        self.assertEqual(planned.status_code, 200)
        execution_id = planned.json()["execution_id"]
        denied = self.client.post(
            "/factory/execution/run",
            json={"execution_id": execution_id},
            headers=self.headers,
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(
            self.client.post(
                "/factory/execution/dry-run",
                json={"execution_id": execution_id},
                headers=self.headers,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/factory/execution/approve",
                json={"execution_id": execution_id},
                headers=self.headers,
            ).status_code,
            200,
        )
        run = self.client.post(
            "/factory/execution/run",
            json={"execution_id": execution_id},
            headers=self.headers,
        )
        self.assertEqual(run.status_code, 200)
        artifacts = self.client.get(
            f"/factory/execution/{execution_id}/artifacts",
            headers=self.headers,
        )
        self.assertGreater(artifacts.json()["total"], 10)
        events = self.client.get(
            f"/factory/execution/{execution_id}/events",
            headers=self.headers,
        )
        self.assertGreater(events.json()["total"], artifacts.json()["total"])
        self.assertTrue(
            (self.output_root / "tenant-a" / "contractor_command_center" / "README.md").is_file()
        )
