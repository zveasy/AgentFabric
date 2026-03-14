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
        prod_db_path = Path(self.tmp.name) / "prod.db"
        self.settings = Settings(
            database_url=f"sqlite:///{db_path}",
            production_db_path=str(prod_db_path),
            redis_url="redis://127.0.0.1:6399/9",  # force fallback to in-memory queue
            jwt_secret="test-secret",
            bootstrap_token="bootstrap-test-token",
            stripe_api_key=None,
        )
        self.client = TestClient(create_app(self.settings))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_auth_and_registry_billing_queue_flow(self) -> None:
        readiness = self.client.get("/health/ready")
        self.assertEqual(readiness.status_code, 200)
        self.assertEqual(readiness.json()["status"], "ok")
        readiness_checks = {item["name"] for item in readiness.json()["checks"]}
        self.assertIn("database", readiness_checks)
        self.assertIn("queue", readiness_checks)

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

        enqueue_dlq = self.client.post("/queue/enqueue", json={"queue_name": "jobs.dlq", "payload": {"kind": "replay-me"}}, headers=headers)
        self.assertEqual(enqueue_dlq.status_code, 200)
        replay = self.client.post("/queue/replay-dlq", json={"queue_name": "jobs", "limit": 5}, headers=headers)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["replayed"], 1)
        replayed = self.client.post("/queue/dequeue", params={"queue_name": "jobs"}, headers=headers)
        self.assertEqual(replayed.status_code, 200)
        self.assertEqual(replayed.json()["payload"]["kind"], "replay-me")

        dlq_messages = self.client.get("/queue/messages", params={"queue_name": "jobs.dlq", "status": "done"}, headers=headers)
        self.assertEqual(dlq_messages.status_code, 200)
        self.assertGreaterEqual(len(dlq_messages.json()["items"]), 1)

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

    def test_enterprise_runtime_reviews_compliance_routes(self) -> None:
        register = self.client.post(
            "/auth/principals/register",
            json={
                "principal_id": "ops-admin",
                "tenant_id": "dev-a",
                "principal_type": "user",
                "scopes": [
                    "auth.token.issue",
                    "runtime.read",
                    "runtime.install",
                    "runtime.run",
                    "enterprise.rbac.write",
                    "enterprise.rbac.read",
                    "enterprise.namespace.write",
                    "enterprise.namespace.read",
                    "enterprise.audit.write",
                    "enterprise.audit.read",
                    "reviews.write",
                    "reviews.moderate",
                    "compliance.gdpr.write",
                    "compliance.legal.write",
                    "compliance.legal.read",
                    "ops.backup.write",
                ],
            },
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        self.assertEqual(register.status_code, 200)
        token_resp = self.client.post(
            "/auth/token/issue",
            json={"principal_id": "ops-admin", "ttl_seconds": 3600},
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        self.assertEqual(token_resp.status_code, 200)
        headers = {"Authorization": f"Bearer {token_resp.json()['access_token']}"}

        runtime_agents = self.client.get("/runtime/agents", headers=headers)
        self.assertEqual(runtime_agents.status_code, 200)
        self.assertIn("items", runtime_agents.json())

        assign = self.client.post(
            "/enterprise/rbac/assign",
            json={"principal_id": "u1", "role": "developer"},
            headers=headers,
        )
        self.assertEqual(assign.status_code, 200)
        check = self.client.post(
            "/enterprise/rbac/check",
            json={"principal_id": "u1", "permission": "registry.publish"},
            headers=headers,
        )
        self.assertEqual(check.status_code, 200)
        self.assertTrue(check.json()["allowed"])

        ns_create = self.client.post(
            "/enterprise/namespace/create",
            json={"owner_tenant_id": "dev-a", "namespace": "dev-a-private"},
            headers=headers,
        )
        self.assertEqual(ns_create.status_code, 200)
        ns_grant = self.client.post(
            "/enterprise/namespace/grant",
            json={"owner_tenant_id": "dev-a", "namespace": "dev-a-private", "target_tenant_id": "dev-a"},
            headers=headers,
        )
        self.assertEqual(ns_grant.status_code, 200)
        ns_check = self.client.post(
            "/enterprise/namespace/check",
            json={"tenant_id": "dev-a", "namespace": "dev-a-private"},
            headers=headers,
        )
        self.assertEqual(ns_check.status_code, 200)

        audit = self.client.post(
            "/enterprise/audit/append",
            json={"actor_id": "ops-admin", "action": "deploy", "target": "svc/api", "metadata": {"sha": "x"}},
            headers=headers,
        )
        self.assertEqual(audit.status_code, 200)
        self.assertIn("event_hash", audit.json())
        integrity = self.client.get("/enterprise/audit/integrity", headers=headers)
        self.assertEqual(integrity.status_code, 200)
        self.assertTrue(integrity.json()["ok"])

        review = self.client.post(
            "/reviews/submit",
            json={
                "tenant_id": "dev-a",
                "package_fqid": "dev-a/alpha:1.0.0",
                "user_id": "u1",
                "stars": 4,
                "review": "looks like malware",
            },
            headers=headers,
        )
        self.assertEqual(review.status_code, 200)
        review_id = review.json()["review_id"]
        pending = self.client.post("/reviews/moderation/pending", headers=headers)
        self.assertEqual(pending.status_code, 200)
        self.assertGreaterEqual(len(pending.json()["items"]), 1)
        resolved = self.client.post(
            "/reviews/moderation/resolve",
            json={"review_id": review_id, "approved": True},
            headers=headers,
        )
        self.assertEqual(resolved.status_code, 200)

        gdpr_req = self.client.post(
            "/compliance/gdpr/request",
            json={"tenant_id": "dev-a", "user_id": "u1", "reason": "request"},
            headers=headers,
        )
        self.assertEqual(gdpr_req.status_code, 200)
        gdpr_process = self.client.post("/compliance/gdpr/process", headers=headers)
        self.assertEqual(gdpr_process.status_code, 200)
        self.assertGreaterEqual(len(gdpr_process.json()["processed"]), 1)

        legal_pub = self.client.post(
            "/compliance/legal/publish",
            json={"doc_type": "tos", "version": "2026-03", "content": "terms"},
            headers=headers,
        )
        self.assertEqual(legal_pub.status_code, 200)
        legal_accept = self.client.post(
            "/compliance/legal/accept",
            json={"doc_type": "tos", "principal_id": "u1"},
            headers=headers,
        )
        self.assertEqual(legal_accept.status_code, 200)
        self.assertEqual(legal_accept.json()["version"], "2026-03")

        backup = self.client.post("/ops/backup", headers=headers)
        self.assertEqual(backup.status_code, 200)
        self.assertIn("backup_file", backup.json())


if __name__ == "__main__":
    unittest.main()
