from __future__ import annotations

import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from agentfabric.errors import ValidationError
from agentfabric.phase2.models import MeterEvent, PackageUpload, Rating
from agentfabric.production.api import ProductionApiServer
from agentfabric.production.control_plane import ProductionControlPlane


def publish_signature(signer_id: str, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    return hashlib.sha256(f"{signer_id}:{digest}:managed".encode("utf-8")).hexdigest()


def runtime_signature(signer_id: str, key: str, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    return hashlib.sha256(f"{signer_id}:{digest}:{key}".encode("utf-8")).hexdigest()


class ProductionStackTests(unittest.TestCase):
    def test_p0_persistence_auth_and_invoice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "prod.db")
            cp = ProductionControlPlane(db_path=db_path)
            cp.auth.register_principal(
                principal_id="dev-a",
                tenant_id="tenant-a",
                principal_type="user",
                scopes=[
                    "registry.publish",
                    "registry.read",
                    "registry.install",
                    "billing.write",
                    "billing.read",
                ],
            )
            token = cp.auth.issue_token("dev-a", ttl_seconds=300)
            cp.auth.authenticate_token(token, required_scopes={"registry.publish"}, tenant_id="tenant-a")
            rotated = cp.auth.rotate_token(token, ttl_seconds=300)
            with self.assertRaises(Exception):
                cp.auth.authenticate_token(token)
            cp.auth.authenticate_token(rotated)

            payload = b"print('safe')"
            upload = PackageUpload(
                package_id="alpha",
                version="1.0.0",
                namespace="dev-a",
                category="research",
                permissions=("tool.web.search",),
                manifest={
                    "manifest_version": "v1",
                    "name": "alpha",
                    "description": "alpha package",
                    "entrypoint": "agent.py:run",
                    "permissions": ["tool.web.search"],
                },
                payload=payload,
                signature=publish_signature("sig-a", payload),
            )
            pkg = cp.publish_package("dev-a", upload, signer_id="sig-a")
            self.assertEqual(pkg.fqid, "dev-a/alpha:1.0.0")

            install = cp.install_package("tenant-a", "user-a", "dev-a", "alpha")
            self.assertEqual(install["package_fqid"], "dev-a/alpha:1.0.0")
            cp.record_billing_event(
                MeterEvent(
                    event_type="run",
                    tenant_id="tenant-a",
                    actor_id="user-a",
                    package_fqid="dev-a/alpha:1.0.0",
                    idempotency_key="run-1",
                )
            )
            cp.record_billing_event(
                MeterEvent(
                    event_type="run",
                    tenant_id="tenant-a",
                    actor_id="user-a",
                    package_fqid="dev-a/alpha:1.0.0",
                    idempotency_key="run-1",
                )
            )
            invoice = cp.build_invoice("tenant-a")
            self.assertGreater(invoice["total"], 0)

            # Persistence check through restart
            cp2 = ProductionControlPlane(db_path=db_path)
            listed = cp2.list_packages()
            self.assertEqual(listed["total"], 1)

    def test_p1_security_ops_runtime_and_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "prod.db")
            cp = ProductionControlPlane(db_path=db_path)

            with self.assertRaises(ValidationError):
                cp.security.validate(
                    signer_id="sig-a",
                    package_name="bad",
                    version="0.1.0",
                    payload=b"rm -rf /",
                    signature="deadbeef",
                )

            manifest = {
                "manifest_version": "v1",
                "agent_id": "example.echo",
                "name": "Echo",
                "description": "echo agent",
                "version": "1.0.0",
                "entrypoint": "agentfabric.cli:EchoAgent",
                "capabilities": ["echo"],
                "permissions": [],
                "sandbox": {"allow_network": False, "allowed_filesystem_paths": []},
                "max_run_seconds": 5,
                "max_tool_calls": 5,
            }
            payload = b"artifact"
            sig = runtime_signature("runtime-signer", "runtime-key", payload)
            cp.install_runtime_agent(
                manifest=manifest,
                payload=payload,
                signer_id="runtime-signer",
                signer_key="runtime-key",
                signature=sig,
            )
            cp.runtime_load("example.echo")
            run = cp.runtime_run(agent_id="example.echo", request={"hello": "world"}, user_id="tenant-a", session_id="s1")
            self.assertIn("correlation_id", run)
            metrics = cp.metrics_prometheus()
            self.assertIn("runtime_run_count", metrics)
            backup = cp.create_backup()
            self.assertTrue(Path(backup).exists())

    def test_p2_moderation_settlement_compliance_legal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "prod.db")
            cp = ProductionControlPlane(db_path=db_path)

            review_id = cp.submit_review(
                Rating(
                    tenant_id="tenant-a",
                    package_fqid="dev-a/alpha:1.0.0",
                    user_id="u1",
                    stars=1,
                    review="looks like malware",
                )
            )
            pending = cp.pending_reviews()
            self.assertEqual(pending[0]["review_id"], review_id)
            cp.moderate_review(review_id, approved=False)

            cp.record_billing_event(
                MeterEvent(
                    event_type="subscription_month",
                    tenant_id="tenant-a",
                    actor_id="system",
                    package_fqid="tenant-plan",
                    idempotency_key="sub-1",
                )
            )
            settled = cp.settle_invoice("tenant-a")
            self.assertIn("transaction_id", settled)

            req_id = cp.request_gdpr_deletion("tenant-a", "u1", "user requested deletion")
            self.assertTrue(req_id.startswith("gdpr-"))
            processed = cp.process_gdpr_deletions()
            self.assertEqual(processed[0], req_id)

            cp.append_audit("admin", "policy.update", "tenant-a")
            siem_path = Path(tmp) / "siem.log"
            exported = cp.export_siem_audit(str(siem_path))
            self.assertTrue(Path(exported).exists())

            cp.publish_legal_document("tos", "2026-03", "terms")
            accepted = cp.accept_legal_document("tos", "u1")
            self.assertEqual(accepted["version"], "2026-03")

    def test_http_api_health_and_auth_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "prod.db")
            cp = ProductionControlPlane(db_path=db_path)
            api = ProductionApiServer(cp)
            server = ThreadingHTTPServer(("127.0.0.1", 0), api.build_handler())
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                conn = http.client.HTTPConnection(host, port, timeout=5)
                conn.request("GET", "/health")
                resp = conn.getresponse()
                body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(resp.status, 200)
                self.assertEqual(body["status"], "ok")

                payload = {
                    "principal_id": "api-user",
                    "tenant_id": "tenant-a",
                    "principal_type": "user",
                    "scopes": ["registry.read"],
                }
                conn.request(
                    "POST",
                    "/auth/principals/register",
                    body=json.dumps(payload),
                    headers={"Content-Type": "application/json"},
                )
                register_resp = conn.getresponse()
                register_resp.read()
                self.assertEqual(register_resp.status, 200)

                conn.request(
                    "POST",
                    "/auth/token/issue",
                    body=json.dumps({"principal_id": "api-user"}),
                    headers={"Content-Type": "application/json"},
                )
                token_resp = conn.getresponse()
                token_payload = json.loads(token_resp.read().decode("utf-8"))
                self.assertEqual(token_resp.status, 200)
                self.assertIn("token", token_payload)
                conn.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
