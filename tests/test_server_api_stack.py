from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from agentfabric.server.app import create_app
from agentfabric.server.config import Settings
from agentfabric.server.database import build_session_factory
from agentfabric.server.models import PaymentRecord, utc_now


class ServerApiStackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "api.db"
        self.settings = Settings(
            database_url=f"sqlite:///{db_path}",
            redis_url="redis://127.0.0.1:6399/9",  # force fallback to in-memory queue
            jwt_secret="test-secret",
            bootstrap_token="bootstrap-test-token",
            stripe_api_key=None,
        )
        self.client = TestClient(create_app(self.settings))

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
                    "metrics.read",
                ],
            },
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        self.assertEqual(register.status_code, 200)

        token_resp = self.client.post(
            "/auth/token/issue",
            json={"principal_id": "dev-a", "ttl_seconds": 3600},
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        self.assertEqual(token_resp.status_code, 200)
        token = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        unauthorized = self.client.get("/registry/list")
        self.assertEqual(unauthorized.status_code, 401)

        blocked_register = self.client.post(
            "/auth/principals/register",
            json={
                "principal_id": "dev-b",
                "tenant_id": "dev-a",
                "principal_type": "user",
                "scopes": [],
            },
        )
        self.assertEqual(blocked_register.status_code, 401)

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

        metrics = self.client.get("/metrics/prometheus", headers=headers)
        self.assertEqual(metrics.status_code, 200)
        self.assertIn("agentfabric_http_requests_total", metrics.text)

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

    def test_strict_signing_requires_cosign_binary(self) -> None:
        strict_db_path = Path(self.tmp.name) / "strict.db"
        with patch("agentfabric.server.app.shutil.which", return_value=None):
            with self.assertRaises(RuntimeError):
                create_app(
                    Settings(
                        database_url=f"sqlite:///{strict_db_path}",
                        redis_url="redis://127.0.0.1:6399/9",
                        jwt_secret="test-secret",
                        strict_signing=True,
                        auto_migrate=False,
                        bootstrap_token="bootstrap-test-token",
                    )
                )

    def test_stripe_webhook_updates_payment_status(self) -> None:
        session_factory, _ = build_session_factory(self.settings)
        with session_factory() as db:
            db.add(
                PaymentRecord(
                    tenant_id="dev-a",
                    provider="stripe",
                    provider_txn_id="pi_12345",
                    amount=5.0,
                    currency="USD",
                    idempotency_key="settle-dev-a-usd",
                    status="pending",
                    updated_at=utc_now(),
                )
            )
            db.commit()

        register = self.client.post(
            "/auth/principals/register",
            json={
                "principal_id": "billing-reader",
                "tenant_id": "dev-a",
                "principal_type": "user",
                "scopes": ["billing.read", "auth.token.issue"],
            },
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        self.assertEqual(register.status_code, 200)
        token_resp = self.client.post(
            "/auth/token/issue",
            json={"principal_id": "billing-reader", "ttl_seconds": 3600},
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        self.assertEqual(token_resp.status_code, 200)
        headers = {"Authorization": f"Bearer {token_resp.json()['access_token']}"}

        webhook = self.client.post(
            "/billing/webhooks/stripe",
            json={
                "type": "payment_intent.succeeded",
                "data": {"object": {"id": "pi_12345", "status": "succeeded"}},
            },
        )
        self.assertEqual(webhook.status_code, 200)
        self.assertEqual(webhook.json()["status"], "succeeded")

        payment = self.client.get("/billing/payments/pi_12345", headers=headers)
        self.assertEqual(payment.status_code, 200)
        self.assertEqual(payment.json()["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
