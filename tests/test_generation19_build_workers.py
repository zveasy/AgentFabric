from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.audit_bundle import AuditBundleExporter
from agentfabric.build_workers import BuildWorkerService
from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError
from agentfabric.events import EventStore
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.repository_execution import RepositoryExecutionEngine
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings


ROOT = Path(__file__).resolve().parents[1]
PLATFORM_ROOT = ROOT / "platforms" / "renovation_os"


class Generation19BuildWorkerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name) / "generated"
        self.store = MemoryPersistenceStore()
        self.events = EventStore(persistence=self.store)
        self.execution = RepositoryExecutionEngine(
            self.store,
            self.events,
            self.output,
            PLATFORM_ROOT,
        )
        self.builds = BuildWorkerService(
            self.store,
            self.events,
            self.execution,
            self.output,
        )
        self.ctx = TenantContext("tenant-a", "org-a", "owner-a", ())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _execution(self, repository: str) -> str:
        plan = self.execution.plan(self.ctx, repository)
        self.execution.approve(self.ctx, plan.execution_id)
        self.execution.execute(self.ctx, plan.execution_id)
        return plan.execution_id

    def test_registry_capabilities_plan_dry_run_approval_execute_review_and_rollback(self) -> None:
        workers = self.builds.registry.list()
        self.assertEqual(len(workers), 7)
        self.assertEqual(
            {item["capability"] for item in workers},
            {
                "domain_models",
                "service_logic",
                "api_routes",
                "tests",
                "documentation",
                "quality_evidence",
                "security_review",
            },
        )
        execution_id = self._execution("reno_estimator")
        scaffold = (
            self.output / "tenant-a" / "reno_estimator" / "src" / "reno_estimator" / "service.py"
        ).read_text(encoding="utf-8")
        plan = self.builds.plan(self.ctx, execution_id)
        build_id = str(plan["build_id"])
        self.assertTrue(all(plan["quality_gates"].values()))
        self.assertEqual(self.builds.dry_run(self.ctx, build_id)["status"], "dry_run_complete")
        with self.assertRaises(AuthorizationError):
            self.builds.execute(self.ctx, build_id)
        self.builds.approve(self.ctx, build_id)
        result = self.builds.execute(self.ctx, build_id)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["marketplace_metadata"]["implementation_status"], "implemented")
        review = self.builds.review(self.ctx, build_id)
        self.assertEqual(review["status"], "approved")
        replay = self.builds.replay(self.ctx, build_id)
        self.assertEqual(replay["output_artifact_hashes"], plan["output_artifact_hashes"])
        service_path = (
            self.output / "tenant-a" / "reno_estimator" / "src" / "reno_estimator" / "service.py"
        )
        self.assertIn("class EstimatorService", service_path.read_text(encoding="utf-8"))
        rollback = self.builds.rollback(self.ctx, build_id)
        self.assertEqual(rollback["status"], "rolled_back")
        self.assertEqual(service_path.read_text(encoding="utf-8"), scaffold)

    def test_tenant_isolation_security_fail_closed_audit_and_hashes(self) -> None:
        execution_id = self._execution("change_order_agent")
        plan = self.builds.plan(self.ctx, execution_id)
        build_id = str(plan["build_id"])
        other = TenantContext("tenant-b", "org-b", "owner-b", ())
        with self.assertRaises(AuthorizationError):
            self.builds.get(other, build_id)
        self.builds.approve(self.ctx, build_id)
        result = self.builds.execute(self.ctx, build_id)
        artifacts = self.builds.artifacts(self.ctx, build_id)
        self.assertEqual(len(artifacts), len(result["output_artifact_hashes"]))
        stored = self.store.get("factory_build_plans", build_id)
        assert stored is not None
        stored["artifact_contents"]["security.review.json"] = json.dumps({"status": "failed"})
        self.store.put("factory_build_plans", build_id, stored)
        with self.assertRaises(AuthorizationError):
            self.builds.review(self.ctx, build_id)
        bundle = AuditBundleExporter(persistence=self.store, event_store=self.events).export("tenant-a").as_dict()
        self.assertTrue(bundle["factory_build_plans"])
        self.assertNotIn("artifact_contents", bundle["factory_build_plans"][0])
        self.assertTrue(bundle["factory_build_approvals"])
        self.assertTrue(bundle["factory_build_results"])
        self.assertTrue(bundle["factory_build_artifacts"])
        self.assertTrue(bundle["event_hash_chain"]["valid"])

    def test_plan_requires_completed_execution(self) -> None:
        plan = self.execution.plan(self.ctx, "contractor_command_center")
        with self.assertRaises(AuthorizationError):
            self.builds.plan(self.ctx, plan.execution_id)
        self.builds.registry._workers.pop("security-review-worker")
        self.execution.approve(self.ctx, plan.execution_id)
        self.execution.execute(self.ctx, plan.execution_id)
        with self.assertRaises(ValueError):
            self.builds.plan(self.ctx, plan.execution_id)

    def test_reference_repositories_run_product_tests(self) -> None:
        for repository in ("reno_estimator", "change_order_agent", "contractor_command_center"):
            root = PLATFORM_ROOT / "repositories" / repository
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "tests"],
                cwd=root,
                env={"PYTHONPATH": str(root / "src")},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            metadata = json.loads((root / "package.manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["implementation_status"], "implemented")
            self.assertEqual(metadata["security_review_status"], "passed")


class Generation19BuildWorkerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name) / "api-generated"
        self.client = TestClient(
            create_app(
                Settings(
                    database_url=f"sqlite:///{Path(self.tmp.name) / 'api.db'}",
                    jwt_secret="test-secret",
                    bootstrap_token="bootstrap-test-token",
                    cloud_queue_backend="memory",
                    rate_limit_auth_per_minute=1000,
                    factory_output_root=str(self.output),
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

    def test_build_api_flow(self) -> None:
        self.assertEqual(self.client.get("/factory/build/workers").status_code, 401)
        execution = self.client.post(
            "/factory/execution/plan",
            json={"repository_id": "change_order_agent"},
            headers=self.headers,
        ).json()
        execution_id = execution["execution_id"]
        self.client.post(
            "/factory/execution/approve",
            json={"execution_id": execution_id},
            headers=self.headers,
        )
        self.client.post(
            "/factory/execution/run",
            json={"execution_id": execution_id},
            headers=self.headers,
        )
        planned = self.client.post(
            "/factory/build/plan",
            json={"execution_id": execution_id},
            headers=self.headers,
        )
        self.assertEqual(planned.status_code, 200)
        build_id = planned.json()["build_id"]
        self.assertEqual(
            self.client.post(
                "/factory/build/run",
                json={"build_id": build_id},
                headers=self.headers,
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/factory/build/dry-run",
                json={"build_id": build_id},
                headers=self.headers,
            ).status_code,
            200,
        )
        self.client.post(
            "/factory/build/approve",
            json={"build_id": build_id},
            headers=self.headers,
        )
        self.assertEqual(
            self.client.post(
                "/factory/build/run",
                json={"build_id": build_id},
                headers=self.headers,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/factory/build/review",
                json={"build_id": build_id, "approved": True},
                headers=self.headers,
            ).status_code,
            200,
        )
        self.assertGreater(
            self.client.get(
                f"/factory/build/{build_id}/artifacts",
                headers=self.headers,
            ).json()["total"],
            5,
        )
        self.assertGreater(
            self.client.get(
                f"/factory/build/{build_id}/events",
                headers=self.headers,
            ).json()["total"],
            5,
        )
