from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.audit_bundle import AuditBundleExporter
from agentfabric.blueprints import BlueprintCatalog
from agentfabric.domain_knowledge import DomainKnowledgeCatalog
from agentfabric.domain_platforms import DomainPlatformCatalog
from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError
from agentfabric.events import EventStore
from agentfabric.marketplace.packages import PackageMetadata
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.repository_factory import RepositoryDependencyGraph, RepositoryFactory
from agentfabric.repository_graph import RepositoryGraph
from agentfabric.repository_lifecycle import RepositoryLifecycleService
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings
from agentfabric.software_factory import SoftwareFoundryService
from agentfabric.software_teams import SoftwareTask, SoftwareTeamService


QUALITY = {
    "architecture_quality": 0.9,
    "code_quality": 0.9,
    "test_coverage": 0.9,
    "documentation_completeness": 0.9,
    "dependency_health": 0.9,
    "observability_readiness": 0.9,
    "security_posture": 0.9,
}


class Generation17SoftwareFactoryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryPersistenceStore()
        self.events = EventStore(persistence=self.store)
        self.ctx = TenantContext("tenant-a", "org-a", "owner-a", ())
        self.foundry = SoftwareFoundryService(self.store, self.events)

    def test_repository_generation_signed_artifacts_and_deterministic_exports(self) -> None:
        idea = self.foundry.create_idea(
            self.ctx,
            {
                "title": "project_cost_service",
                "domain": "construction",
                "purpose": "Track renovation costs",
                "repository_type": "service",
            },
        )
        repository, package = self.foundry.generate_repository(
            self.ctx,
            {
                "idea_id": idea.idea_id,
                "quality_metrics": QUALITY,
            },
        )
        self.assertEqual(package.status, "validated")
        self.assertEqual(len(package.artifacts), 12)
        self.assertTrue(all(len(item.signature) == 64 for item in package.artifacts))
        self.assertEqual(repository.repository_id, package.repository_id)

        factory = RepositoryFactory()
        first = factory.create_blueprint(
            {
                "name": "deterministic_service",
                "domain": "construction",
                "purpose": "Deterministic export",
                "repository_type": "service",
            }
        )
        second = factory.create_blueprint(
            {
                "purpose": "Deterministic export",
                "repository_type": "service",
                "domain": "construction",
                "name": "deterministic_service",
            }
        )
        self.assertEqual(first.manifest.export_json(), second.manifest.export_json())
        self.assertEqual(first.digest, second.digest)

    def test_blueprints_platforms_knowledge_dependency_graph_and_renovation_seed(self) -> None:
        blueprint = BlueprintCatalog().get("construction")
        self.assertIn("construction:read", blueprint.rbac_scopes)
        self.assertEqual(json.loads(blueprint.export_json())["category"], "construction")
        platform = DomainPlatformCatalog().get("RenovationOS")
        self.assertEqual(len(platform.package_graph), 9)
        self.assertIn("reno_estimator", platform.package_graph["change_order_agent"])
        knowledge = DomainKnowledgeCatalog().get("construction")
        self.assertEqual(knowledge.domain, "construction")
        metadata = PackageMetadata.from_dict(
            {
                "category": "construction",
                "bundle_id": "renovation-os",
                "compatibility": {"AgentFabric": ">=1.0.0"},
                "quality_score": 0.95,
            }
        )
        self.assertEqual(metadata.category, "construction")
        self.assertEqual(metadata.bundle_id, "renovation-os")
        self.assertEqual(metadata.compatibility["AgentFabric"], ">=1.0.0")

        graph = RepositoryDependencyGraph()
        graph.add("repo-a", ())
        graph.add("repo-b", ("repo-a",))
        self.assertEqual(graph.dependencies("repo-b"), ("repo-a",))
        with self.assertRaises(ValueError):
            graph.add("repo-a", ("repo-b",))

        root = Path(__file__).resolve().parents[1] / "platforms/renovation_os"
        definitions = [path for path in root.glob("*.json") if path.name != "platform.json"]
        self.assertEqual(len(definitions), 9)
        for path in definitions:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload["apis"])
            self.assertTrue(payload["events"])
            self.assertTrue(payload["rbac_scopes"])
            self.assertTrue(payload["metrics"])
            self.assertTrue(payload["tests"])
            self.assertTrue(payload["deployment_requirements"])

    def test_lifecycle_teams_lineage_quality_fail_closed_and_audit(self) -> None:
        blueprint = RepositoryFactory().create_blueprint(
            {
                "name": "lifecycle_service",
                "domain": "construction",
                "purpose": "Lifecycle test",
                "repository_type": "service",
                "dependencies": ("shared-module",),
            }
        )
        lifecycle = RepositoryLifecycleService(self.store, self.events)
        created = lifecycle.create(self.ctx, blueprint)
        archived = lifecycle.archive(self.ctx, created.repository_id)
        self.assertEqual(archived.status, "archived")
        restored = lifecycle.restore(self.ctx, created.repository_id)
        self.assertEqual(restored.status, "active")
        updated = lifecycle.update(self.ctx, created.repository_id, blueprint.manifest, "1.1.0")
        self.assertEqual(updated.release_history[-1], "1.1.0")
        deprecated = lifecycle.deprecate(self.ctx, created.repository_id)
        self.assertEqual(deprecated.status, "deprecated")
        lifecycle.restore(self.ctx, created.repository_id)
        cloned = lifecycle.clone(self.ctx, created.repository_id, "lifecycle_clone")
        forked = lifecycle.fork(self.ctx, created.repository_id, "lifecycle_fork")
        graph = RepositoryGraph(lifecycle.list(self.ctx))
        lineage = graph.lineage()
        self.assertTrue(any(item["parent_repository_id"] == created.repository_id for item in lineage))
        self.assertEqual(graph.impact(created.repository_id).direct_dependents, ())
        self.assertEqual(graph.impact(created.repository_id).drifted_dependencies, ("shared-module",))
        self.assertEqual(forked.lineage_action, "fork")
        self.assertEqual(cloned.lineage_action, "clone")

        task = SoftwareTeamService(self.store, self.events).assign(
            SoftwareTask(
                tenant_id="tenant-a",
                repository_id=created.repository_id,
                team="Security Team",
                description="Review repository security posture",
                assigned_agents=("security-agent",),
            )
        )
        self.assertEqual(task.team, "Security Team")

        idea = self.foundry.create_idea(
            self.ctx,
            {
                "title": "weak_service",
                "domain": "construction",
                "purpose": "Quality gate test",
                "repository_type": "service",
            },
        )
        with self.assertRaises(AuthorizationError):
            self.foundry.generate_repository(
                self.ctx,
                {
                    "idea_id": idea.idea_id,
                    "quality_metrics": {**QUALITY, "security_posture": 0.2},
                },
            )
        other_ctx = TenantContext("tenant-b", "org-b", "owner-b", ())
        with self.assertRaises(AuthorizationError):
            self.foundry.generate_repository(
                other_ctx,
                {"idea_id": idea.idea_id, "quality_metrics": QUALITY},
            )
        self.assertTrue(any(event.event_type == "factory.quality.failed" for event in self.events.replay()))

        bundle = AuditBundleExporter(persistence=self.store, event_store=self.events).export("tenant-a").as_dict()
        self.assertTrue(bundle["factory_repositories"])
        self.assertTrue(bundle["factory_tasks"])
        self.assertTrue(bundle["event_hash_chain"]["valid"])


class Generation17SoftwareFactoryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.client = TestClient(
            create_app(
                Settings(
                    database_url=f"sqlite:///{Path(self.tmp.name) / 'api.db'}",
                    jwt_secret="test-secret",
                    bootstrap_token="bootstrap-test-token",
                    cloud_queue_backend="memory",
                    rate_limit_auth_per_minute=1000,
                )
            )
        )
        self.headers = self._principal("owner-a", "tenant-a", "owner")
        tenant = self.client.post(
            "/tenants",
            json={"tenant_id": "tenant-a", "organization_id": "org-a", "name": "Tenant A", "billing_plan": "enterprise"},
            headers=self.headers,
        )
        self.assertEqual(tenant.status_code, 200)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _principal(self, principal_id: str, tenant_id: str, role: str) -> dict[str, str]:
        registration_headers = (
            self.headers
            if hasattr(self, "headers")
            else {"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"}
        )
        self.client.post(
            "/auth/principals/register",
            json={"principal_id": principal_id, "tenant_id": tenant_id, "role": role, "scopes": []},
            headers=registration_headers,
        )
        token = self.client.post(
            "/auth/token/issue",
            json={"principal_id": principal_id},
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        return {"Authorization": f"Bearer {token.json()['access_token']}"}

    def test_factory_apis_tenant_isolation_rbac_and_quality(self) -> None:
        self.assertEqual(self.client.get("/factory/repositories").status_code, 401)
        idea = self.client.post(
            "/factory/ideas",
            json={
                "title": "reno_schedule_service",
                "domain": "construction",
                "purpose": "Coordinate renovation schedules",
                "repository_type": "service",
            },
            headers=self.headers,
        )
        self.assertEqual(idea.status_code, 200)
        generated = self.client.post(
            "/factory/repositories",
            json={"idea_id": idea.json()["idea_id"], "quality_metrics": QUALITY},
            headers=self.headers,
        )
        self.assertEqual(generated.status_code, 200)
        repository_id = generated.json()["repository"]["repository_id"]
        self.assertEqual(self.client.get("/factory/repositories", headers=self.headers).json()["total"], 1)
        self.assertEqual(
            self.client.get(f"/factory/repositories/{repository_id}", headers=self.headers).status_code,
            200,
        )
        self.assertEqual(self.client.get("/factory/platforms", headers=self.headers).json()["total"], 7)
        registered = self.client.post(
            "/factory/platforms",
            json={"name": "RenovationOS"},
            headers=self.headers,
        )
        self.assertEqual(registered.status_code, 200)
        self.assertTrue(self.client.get("/factory/lineage", headers=self.headers).json()["items"])
        self.assertIn("dependencies", self.client.get("/factory/dependencies", headers=self.headers).json())
        self.assertEqual(self.client.get("/factory/quality", headers=self.headers).json()["total"], 1)

        viewer_headers = self._principal("viewer-a", "tenant-a", "viewer")
        denied = self.client.post(
            "/factory/ideas",
            json={
                "title": "denied",
                "domain": "construction",
                "purpose": "Denied",
                "repository_type": "service",
            },
            headers=viewer_headers,
        )
        self.assertEqual(denied.status_code, 403)


if __name__ == "__main__":
    unittest.main()
