from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.server.app import create_app
from agentfabric.server.config import Settings


class ServerApiStackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "api.db"
        settings = Settings(
            database_url=f"sqlite:///{db_path}",
            redis_url="redis://127.0.0.1:6399/9",  # force fallback to in-memory queue
            jwt_secret="test-secret-at-least-32-characters-long-for-hmac",
            stripe_api_key=None,
        )
        self.client = TestClient(create_app(settings))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_auth_and_registry_billing_queue_flow(self) -> None:
        register = self.client.post(
            "/auth/principals/register",
            json={
                "principal_id": "dev-a",
                "tenant_id": "dev-a",
                "principal_type": "user",
                "scopes": [
                    "registry.publish",
                    "registry.read",
                    "registry.install",
                    "billing.write",
                    "billing.read",
                    "queue.write",
                    "queue.read",
                    "projects.read",
                    "projects.manage",
                    "projects.contribute",
                    "projects.evaluate",
                ],
            },
        )
        self.assertEqual(register.status_code, 200)

        token_resp = self.client.post("/auth/token/issue", json={"principal_id": "dev-a", "ttl_seconds": 3600})
        self.assertEqual(token_resp.status_code, 200)
        token = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        register_contrib = self.client.post(
            "/auth/principals/register",
            json={
                "principal_id": "contrib-1",
                "tenant_id": "community-contrib",
                "principal_type": "user",
                "scopes": ["projects.contribute", "projects.read"],
            },
        )
        self.assertEqual(register_contrib.status_code, 200)
        contrib_token_resp = self.client.post("/auth/token/issue", json={"principal_id": "contrib-1", "ttl_seconds": 3600})
        self.assertEqual(contrib_token_resp.status_code, 200)
        contrib_headers = {"Authorization": f"Bearer {contrib_token_resp.json()['access_token']}"}

        unauthorized = self.client.get("/registry/list")
        self.assertEqual(unauthorized.status_code, 401)
        forge = self.client.get("/forge")
        self.assertEqual(forge.status_code, 200)
        self.assertIn("AgentForge", forge.text)

        payload = "print('hello')"
        signature = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        publish = self.client.post(
            "/registry/publish",
            json={
                "namespace": "dev-a",
                "package_id": "alpha",
                "version": "1.0.0",
                "category": "research",
                "permissions": ["tool.web.search"],
                "manifest": {
                    "manifest_version": "v1",
                    "name": "alpha",
                    "description": "alpha package",
                    "entrypoint": "agent.py:run",
                    "permissions": ["tool.web.search"],
                },
                "payload": payload,
                "signature": signature,
                "signer_id": "dev-a",
            },
            headers=headers,
        )
        self.assertEqual(publish.status_code, 200)
        self.assertEqual(publish.json()["fqid"], "dev-a/alpha:1.0.0")

        listed = self.client.get("/registry/list", headers=headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["total"], 1)

        install = self.client.post(
            "/registry/install",
            json={
                "tenant_id": "dev-a",
                "user_id": "u1",
                "namespace": "dev-a",
                "package_id": "alpha",
                "version": "1.0.0",
            },
            headers=headers,
        )
        self.assertEqual(install.status_code, 200)

        evt = self.client.post(
            "/billing/events",
            json={
                "tenant_id": "dev-a",
                "actor_id": "u1",
                "event_type": "run",
                "package_fqid": "dev-a/alpha:1.0.0",
                "idempotency_key": "evt-1",
            },
            headers=headers,
        )
        self.assertEqual(evt.status_code, 200)
        self.assertTrue(evt.json()["processed"])

        invoice = self.client.get("/billing/invoice", params={"tenant_id": "dev-a"}, headers=headers)
        self.assertEqual(invoice.status_code, 200)
        self.assertGreater(invoice.json()["total"], 0)

        enqueue = self.client.post("/queue/enqueue", json={"queue_name": "jobs", "payload": {"kind": "demo"}}, headers=headers)
        self.assertEqual(enqueue.status_code, 200)
        dequeue = self.client.post("/queue/dequeue", params={"queue_name": "jobs"}, headers=headers)
        self.assertEqual(dequeue.status_code, 200)
        self.assertEqual(dequeue.json()["payload"]["kind"], "demo")

        rotate = self.client.post("/auth/token/rotate", json={"ttl_seconds": 3600}, headers=headers)
        self.assertEqual(rotate.status_code, 200)
        new_token = rotate.json()["access_token"]
        old_headers = headers
        headers = {"Authorization": f"Bearer {new_token}"}
        old_unauth = self.client.get("/registry/list", headers=old_headers)
        self.assertEqual(old_unauth.status_code, 401)
        still_auth = self.client.get("/registry/list", headers=headers)
        self.assertEqual(still_auth.status_code, 200)

        create_project = self.client.post(
            "/projects",
            json={
                "namespace": "dev-a",
                "project_id": "research-agent",
                "display_name": "Research Agent",
                "description": "Depth-first managed agent project.",
                "contribution_zones": ["tool_adapters", "domain_packs", "workflow_steps"],
                "merge_policy": {"min_improvements": 1, "allowed_latency_regression_pct": 4.0},
            },
            headers=headers,
        )
        self.assertEqual(create_project.status_code, 200)
        self.assertEqual(create_project.json()["project_id"], "research-agent")
        self.assertIn("main", [b["branch_name"] for b in create_project.json()["branches"]])

        create_branch = self.client.post(
            "/projects/dev-a/research-agent/branches",
            json={"branch_name": "improved-citation-module", "base_ref": "main"},
            headers=headers,
        )
        self.assertEqual(create_branch.status_code, 200)
        self.assertEqual(create_branch.json()["branch_name"], "improved-citation-module")

        submit_contribution = self.client.post(
            "/projects/dev-a/research-agent/contributions",
            json={
                "branch_name": "improved-citation-module",
                "title": "Improve source citation precision",
                "summary": "Adds citation normalization and confidence thresholding.",
                "contribution_zone": "workflow_steps",
                "contribution_manifest": {
                    "what_changed": ["citation normalization", "source confidence weighting"],
                    "why_it_matters": "Higher citation precision and lower hallucination risk.",
                },
                "metrics": {
                    "improvements": {"accuracy": 0.08, "reliability": 0.05},
                    "safety_passed": True,
                    "regression_tests_passed": True,
                    "evaluation_score": 92.4,
                },
                "regressions": {"latency_regression_pct": 1.8, "cost_regression_pct": 0.9},
            },
            headers=contrib_headers,
        )
        self.assertEqual(submit_contribution.status_code, 200)
        contribution_id = submit_contribution.json()["contribution_id"]
        pending_contributions = self.client.get("/projects/dev-a/research-agent/contributions", headers=headers)
        self.assertEqual(pending_contributions.status_code, 200)
        self.assertGreaterEqual(pending_contributions.json()["total"], 1)
        self.assertEqual(pending_contributions.json()["items"][0]["contribution_id"], contribution_id)

        evaluate = self.client.post(
            f"/projects/dev-a/research-agent/contributions/{contribution_id}/evaluate",
            headers=headers,
        )
        self.assertEqual(evaluate.status_code, 200)
        self.assertTrue(evaluate.json()["gate_passed"])

        review_merge = self.client.post(
            f"/projects/dev-a/research-agent/contributions/{contribution_id}/review",
            json={
                "decision": "merge",
                "decision_notes": "Improves citation quality without meaningful regressions.",
                "release_version": "1.1.0",
                "release_channel": "stable",
            },
            headers=headers,
        )
        self.assertEqual(review_merge.status_code, 200)
        self.assertEqual(review_merge.json()["status"], "merged")

        releases = self.client.get("/projects/dev-a/research-agent/releases", params={"channel": "stable"}, headers=headers)
        self.assertEqual(releases.status_code, 200)
        self.assertEqual(releases.json()["items"][0]["version"], "1.1.0")

        failing = self.client.post(
            "/projects/dev-a/research-agent/contributions",
            json={
                "branch_name": "improved-citation-module",
                "title": "Unproven experimental tweak",
                "summary": "No measurable upside.",
                "contribution_zone": "workflow_steps",
                "contribution_manifest": {"what_changed": ["minor refactor"]},
                "metrics": {
                    "improvements": {},
                    "safety_passed": True,
                    "regression_tests_passed": False,
                    "evaluation_score": 40.0,
                },
                "regressions": {"latency_regression_pct": 8.5, "cost_regression_pct": 6.1},
            },
            headers=contrib_headers,
        )
        self.assertEqual(failing.status_code, 200)
        failing_id = failing.json()["contribution_id"]

        evaluate_failing = self.client.post(
            f"/projects/dev-a/research-agent/contributions/{failing_id}/evaluate",
            headers=headers,
        )
        self.assertEqual(evaluate_failing.status_code, 200)
        self.assertFalse(evaluate_failing.json()["gate_passed"])
        rejected = self.client.get(
            "/projects/dev-a/research-agent/contributions",
            params={"status": "rejected"},
            headers=headers,
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["items"][0]["contribution_id"], failing_id)

        denied_merge = self.client.post(
            f"/projects/dev-a/research-agent/contributions/{failing_id}/review",
            json={
                "decision": "merge",
                "decision_notes": "Should not merge due to failed gate.",
                "release_version": "1.2.0",
                "release_channel": "stable",
            },
            headers=headers,
        )
        self.assertEqual(denied_merge.status_code, 400)


if __name__ == "__main__":
    unittest.main()
