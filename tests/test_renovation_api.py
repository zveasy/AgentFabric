from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.server.app import create_app
from agentfabric.server.config import Settings

from tests.renovation_helpers import (
    CHANGE_ORDER_PAYLOAD,
    DAILY_LOG_PAYLOAD,
    ESTIMATE_PAYLOAD,
    FIELD_NOTE_PAYLOAD,
    JOB_PAYLOAD,
    PROPOSAL_PAYLOAD,
)


class RenovationApiTests(unittest.TestCase):
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

    def test_authenticated_estimate_proposal_get_and_export_flow(self) -> None:
        self.assertEqual(self.client.post("/renovation/estimate", json=ESTIMATE_PAYLOAD).status_code, 401)
        estimate = self.client.post(
            "/renovation/estimate",
            json=ESTIMATE_PAYLOAD,
            headers=self.headers,
        )
        self.assertEqual(estimate.status_code, 200)
        estimate_id = estimate.json()["estimate_id"]
        self.assertEqual(
            self.client.get(
                f"/renovation/estimate/{estimate_id}",
                headers=self.headers,
            ).status_code,
            200,
        )
        proposal = self.client.post(
            "/renovation/proposal",
            json={**PROPOSAL_PAYLOAD, "estimate_id": estimate_id},
            headers=self.headers,
        )
        self.assertEqual(proposal.status_code, 200)
        proposal_id = proposal.json()["proposal_id"]
        self.assertEqual(
            self.client.get(
                f"/renovation/proposal/{proposal_id}",
                headers=self.headers,
            ).status_code,
            200,
        )
        exported = self.client.post(
            "/renovation/proposal/export",
            json={"proposal_id": proposal_id, "format": "text"},
            headers=self.headers,
        )
        self.assertEqual(exported.status_code, 200)
        self.assertIn("Payment Schedule", exported.json()["content"])

        viewer_headers = self._principal("viewer-a", "tenant-a", "viewer")
        self.assertEqual(
            self.client.get(
                f"/renovation/estimate/{estimate_id}",
                headers=viewer_headers,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/renovation/estimate",
                json=ESTIMATE_PAYLOAD,
                headers=viewer_headers,
            ).status_code,
            403,
        )

    def test_job_documentation_change_order_and_approval_apis(self) -> None:
        estimate_id = self.client.post(
            "/renovation/estimate",
            json=ESTIMATE_PAYLOAD,
            headers=self.headers,
        ).json()["estimate_id"]
        proposal_id = self.client.post(
            "/renovation/proposal",
            json={**PROPOSAL_PAYLOAD, "estimate_id": estimate_id},
            headers=self.headers,
        ).json()["proposal_id"]
        job = self.client.post(
            "/renovation/jobs",
            json={**JOB_PAYLOAD, "proposal_id": proposal_id},
            headers=self.headers,
        )
        self.assertEqual(job.status_code, 200)
        job_id = job.json()["job_id"]
        log = self.client.post(
            f"/renovation/jobs/{job_id}/daily-log",
            json=DAILY_LOG_PAYLOAD,
            headers=self.headers,
        )
        self.assertEqual(log.status_code, 200)
        self.assertEqual(log.json()["daily_summary"]["work_date"], "2026-07-08")
        self.assertEqual(
            self.client.post(
                f"/renovation/jobs/{job_id}/field-note",
                json=FIELD_NOTE_PAYLOAD,
                headers=self.headers,
            ).status_code,
            200,
        )
        order = self.client.post(
            "/renovation/change-orders",
            json={**CHANGE_ORDER_PAYLOAD, "job_id": job_id},
            headers=self.headers,
        )
        self.assertEqual(order.status_code, 200)
        change_order_id = order.json()["change_order_id"]
        viewer = self._principal("viewer-r2", "tenant-a", "viewer")
        self.assertEqual(
            self.client.post(
                f"/renovation/change-orders/{change_order_id}/approve",
                json={"decision_date": "2026-07-09"},
                headers=viewer,
            ).status_code,
            403,
        )
        approved = self.client.post(
            f"/renovation/change-orders/{change_order_id}/approve",
            json={"decision_date": "2026-07-09", "decided_by": "Customer"},
            headers=self.headers,
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "approved")
        self.assertEqual(
            self.client.get(
                f"/renovation/change-orders/{change_order_id}",
                headers=viewer,
            ).status_code,
            200,
        )
        exported = self.client.post(
            f"/renovation/change-orders/{change_order_id}/export",
            json={"format": "text"},
            headers=self.headers,
        )
        self.assertEqual(exported.status_code, 200)
        self.assertIn("Change Order", exported.json()["content"])
        history = self.client.get(
            f"/renovation/jobs/{job_id}",
            headers=self.headers,
        )
        self.assertEqual(history.status_code, 200)
        self.assertTrue(history.json()["history"]["change_orders"])
