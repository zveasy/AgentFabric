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
                ],
            },
        )
        self.assertEqual(register.status_code, 200)

        token_resp = self.client.post("/auth/token/issue", json={"principal_id": "dev-a", "ttl_seconds": 3600})
        self.assertEqual(token_resp.status_code, 200)
        token = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        unauthorized = self.client.get("/registry/list")
        self.assertEqual(unauthorized.status_code, 401)

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


if __name__ == "__main__":
    unittest.main()
