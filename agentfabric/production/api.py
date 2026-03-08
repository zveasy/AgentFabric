"""Hosted HTTP API for production control plane."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from agentfabric.errors import AgentFabricError, AuthorizationError, NotFoundError, ValidationError
from agentfabric.phase2.models import MeterEvent, PackageUpload, Rating
from agentfabric.production.authn import TokenAuthService
from agentfabric.production.control_plane import ProductionControlPlane


class ProductionApiServer:
    """Simple JSON HTTP server exposing control-plane endpoints."""

    def __init__(self, control_plane: ProductionControlPlane) -> None:
        self.control_plane = control_plane

    def build_handler(self):  # type: ignore[override]
        control_plane = self.control_plane

        class Handler(BaseHTTPRequestHandler):
            server_version = "AgentFabricProductionAPI/1.0"

            def _send_json(self, status_code: int, payload: dict) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _read_json(self) -> dict:
                length = int(self.headers.get("Content-Length", "0"))
                if length == 0:
                    return {}
                return json.loads(self.rfile.read(length).decode("utf-8"))

            def _require_principal(self, *, scopes: set[str] | None = None, tenant_id: str | None = None):
                token = TokenAuthService.parse_bearer(self.headers.get("Authorization"))
                return control_plane.auth.authenticate_token(token, required_scopes=scopes, tenant_id=tenant_id)

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                try:
                    if parsed.path == "/health":
                        self._send_json(200, {"status": "ok"})
                        return
                    if parsed.path == "/registry/list":
                        self._require_principal(scopes={"registry.read"})
                        params = parse_qs(parsed.query)
                        page = int(params.get("page", ["1"])[0])
                        page_size = int(params.get("page_size", ["20"])[0])
                        permissions = set(params.get("permission", [])) or None
                        result = control_plane.list_packages(
                            query=params.get("query", [None])[0],
                            category=params.get("category", [None])[0],
                            required_permissions=permissions,
                            page=page,
                            page_size=page_size,
                        )
                        self._send_json(200, result)
                        return
                    if parsed.path == "/runtime/agents":
                        self._require_principal(scopes={"runtime.read"})
                        self._send_json(200, {"items": control_plane.runtime_agents()})
                        return
                    if parsed.path == "/billing/invoice":
                        params = parse_qs(parsed.query)
                        tenant_id = params["tenant_id"][0]
                        self._require_principal(scopes={"billing.read"}, tenant_id=tenant_id)
                        self._send_json(200, control_plane.build_invoice(tenant_id))
                        return
                    if parsed.path == "/metrics/prometheus":
                        self._require_principal(scopes={"metrics.read"})
                        self.send_response(200)
                        body = control_plane.metrics_prometheus().encode("utf-8")
                        self.send_header("Content-Type", "text/plain; version=0.0.4")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return
                    self._send_json(404, {"error": "not found"})
                except Exception as exc:  # pragma: no cover - HTTP path handling
                    self._handle_error(exc)

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                try:
                    payload = self._read_json()
                    if parsed.path == "/auth/principals/register":
                        control_plane.auth.register_principal(
                            principal_id=payload["principal_id"],
                            tenant_id=payload["tenant_id"],
                            principal_type=payload.get("principal_type", "user"),
                            scopes=payload.get("scopes", []),
                        )
                        self._send_json(
                            200,
                            {
                                "status": "ok",
                                "principal_id": payload["principal_id"],
                            },
                        )
                        return
                    if parsed.path == "/auth/token/issue":
                        token = control_plane.auth.issue_token(payload["principal_id"], ttl_seconds=int(payload.get("ttl_seconds", 3600)))
                        self._send_json(200, {"token": token})
                        return
                    if parsed.path == "/auth/token/rotate":
                        new_token = control_plane.auth.rotate_token(payload["token"], ttl_seconds=int(payload.get("ttl_seconds", 3600)))
                        self._send_json(200, {"token": new_token})
                        return

                    if parsed.path == "/registry/publish":
                        principal = self._require_principal(scopes={"registry.publish"})
                        upload = PackageUpload(
                            package_id=payload["package_id"],
                            version=payload["version"],
                            namespace=payload["namespace"],
                            category=payload["category"],
                            permissions=tuple(payload.get("permissions", [])),
                            manifest=payload["manifest"],
                            payload=payload["payload"].encode("utf-8"),
                            signature=payload["signature"],
                        )
                        package = control_plane.publish_package(
                            developer_id=principal.principal_id,
                            upload=upload,
                            signer_id=payload["signer_id"],
                        )
                        self._send_json(200, {"fqid": package.fqid})
                        return
                    if parsed.path == "/registry/install":
                        tenant_id = payload["tenant_id"]
                        self._require_principal(scopes={"registry.install"}, tenant_id=tenant_id)
                        result = control_plane.install_package(
                            tenant_id=tenant_id,
                            user_id=payload["user_id"],
                            namespace=payload["namespace"],
                            package_id=payload["package_id"],
                            version=payload.get("version"),
                        )
                        self._send_json(200, result)
                        return

                    if parsed.path == "/runtime/install":
                        self._require_principal(scopes={"runtime.install"})
                        agent_id = control_plane.install_runtime_agent(
                            manifest=payload["manifest"],
                            payload=payload["payload"].encode("utf-8"),
                            signer_id=payload["signer_id"],
                            signer_key=payload["signer_key"],
                            signature=payload["signature"],
                        )
                        self._send_json(200, {"agent_id": agent_id})
                        return
                    if parsed.path == "/runtime/load":
                        self._require_principal(scopes={"runtime.run"})
                        control_plane.runtime_load(payload["agent_id"])
                        self._send_json(200, {"status": "loaded"})
                        return
                    if parsed.path == "/runtime/run":
                        self._require_principal(scopes={"runtime.run"})
                        result = control_plane.runtime_run(
                            agent_id=payload["agent_id"],
                            request=payload["request"],
                            user_id=payload["user_id"],
                            session_id=payload["session_id"],
                        )
                        self._send_json(200, result)
                        return
                    if parsed.path == "/runtime/suspend":
                        self._require_principal(scopes={"runtime.run"})
                        control_plane.runtime_suspend(payload["agent_id"])
                        self._send_json(200, {"status": "suspended"})
                        return
                    if parsed.path == "/runtime/uninstall":
                        self._require_principal(scopes={"runtime.install"})
                        control_plane.runtime_uninstall(payload["agent_id"])
                        self._send_json(200, {"status": "uninstalled"})
                        return

                    if parsed.path == "/billing/events":
                        tenant_id = payload["tenant_id"]
                        self._require_principal(scopes={"billing.write"}, tenant_id=tenant_id)
                        processed = control_plane.record_billing_event(
                            MeterEvent(
                                event_type=payload["event_type"],
                                tenant_id=tenant_id,
                                actor_id=payload["actor_id"],
                                package_fqid=payload["package_fqid"],
                                idempotency_key=payload["idempotency_key"],
                            )
                        )
                        self._send_json(200, {"processed": processed})
                        return
                    if parsed.path == "/billing/settle":
                        tenant_id = payload["tenant_id"]
                        self._require_principal(scopes={"billing.write"}, tenant_id=tenant_id)
                        result = control_plane.settle_invoice(tenant_id=tenant_id, currency=payload.get("currency", "USD"))
                        self._send_json(200, result)
                        return

                    if parsed.path == "/enterprise/rbac/assign":
                        self._require_principal(scopes={"enterprise.rbac.write"})
                        control_plane.assign_role(payload["principal_id"], payload["role"])
                        self._send_json(200, {"status": "ok"})
                        return
                    if parsed.path == "/enterprise/rbac/check":
                        self._require_principal(scopes={"enterprise.rbac.read"})
                        control_plane.check_permission(payload["principal_id"], payload["permission"])
                        self._send_json(200, {"allowed": True})
                        return
                    if parsed.path == "/enterprise/namespace/create":
                        self._require_principal(scopes={"enterprise.namespace.write"}, tenant_id=payload["owner_tenant_id"])
                        control_plane.create_namespace(payload["owner_tenant_id"], payload["namespace"])
                        self._send_json(200, {"status": "created"})
                        return
                    if parsed.path == "/enterprise/namespace/grant":
                        self._require_principal(scopes={"enterprise.namespace.write"}, tenant_id=payload["owner_tenant_id"])
                        control_plane.grant_namespace_access(
                            payload["owner_tenant_id"],
                            payload["namespace"],
                            payload["target_tenant_id"],
                        )
                        self._send_json(200, {"status": "granted"})
                        return
                    if parsed.path == "/enterprise/namespace/check":
                        self._require_principal(scopes={"enterprise.namespace.read"}, tenant_id=payload["tenant_id"])
                        control_plane.check_namespace_access(payload["tenant_id"], payload["namespace"])
                        self._send_json(200, {"allowed": True})
                        return
                    if parsed.path == "/enterprise/audit/append":
                        self._require_principal(scopes={"enterprise.audit.write"})
                        hashes = control_plane.append_audit(
                            actor_id=payload["actor_id"],
                            action=payload["action"],
                            target=payload["target"],
                            metadata=payload.get("metadata", {}),
                        )
                        self._send_json(200, hashes)
                        return
                    if parsed.path == "/enterprise/audit/export":
                        self._require_principal(scopes={"enterprise.audit.read"})
                        path = control_plane.export_siem_audit(payload["output_file"])
                        self._send_json(200, {"path": path})
                        return

                    if parsed.path == "/reviews/submit":
                        self._require_principal(scopes={"reviews.write"}, tenant_id=payload["tenant_id"])
                        review_id = control_plane.submit_review(
                            Rating(
                                tenant_id=payload["tenant_id"],
                                package_fqid=payload["package_fqid"],
                                user_id=payload["user_id"],
                                stars=int(payload["stars"]),
                                review=payload["review"],
                            )
                        )
                        self._send_json(200, {"review_id": review_id})
                        return
                    if parsed.path == "/reviews/moderation/pending":
                        self._require_principal(scopes={"reviews.moderate"})
                        self._send_json(200, {"items": control_plane.pending_reviews()})
                        return
                    if parsed.path == "/reviews/moderation/resolve":
                        self._require_principal(scopes={"reviews.moderate"})
                        control_plane.moderate_review(int(payload["review_id"]), approved=bool(payload["approved"]))
                        self._send_json(200, {"status": "ok"})
                        return

                    if parsed.path == "/compliance/gdpr/request":
                        self._require_principal(scopes={"compliance.gdpr.write"}, tenant_id=payload["tenant_id"])
                        request_id = control_plane.request_gdpr_deletion(
                            tenant_id=payload["tenant_id"],
                            user_id=payload.get("user_id"),
                            reason=payload["reason"],
                        )
                        self._send_json(200, {"request_id": request_id})
                        return
                    if parsed.path == "/compliance/gdpr/process":
                        self._require_principal(scopes={"compliance.gdpr.write"})
                        processed = control_plane.process_gdpr_deletions()
                        self._send_json(200, {"processed": processed})
                        return
                    if parsed.path == "/compliance/legal/publish":
                        self._require_principal(scopes={"compliance.legal.write"})
                        control_plane.publish_legal_document(
                            payload["doc_type"],
                            payload["version"],
                            payload["content"],
                        )
                        self._send_json(200, {"status": "ok"})
                        return
                    if parsed.path == "/compliance/legal/accept":
                        self._require_principal(scopes={"compliance.legal.read"})
                        doc = control_plane.accept_legal_document(payload["doc_type"], payload["principal_id"])
                        self._send_json(200, doc)
                        return

                    if parsed.path == "/ops/backup":
                        self._require_principal(scopes={"ops.backup.write"})
                        backup = control_plane.create_backup()
                        self._send_json(200, {"backup_file": backup})
                        return
                    self._send_json(404, {"error": "not found"})
                except Exception as exc:  # pragma: no cover - HTTP path handling
                    self._handle_error(exc)

            def _handle_error(self, exc: Exception) -> None:
                if isinstance(exc, AuthorizationError):
                    self._send_json(403, {"error": str(exc)})
                    return
                if isinstance(exc, (ValidationError, AgentFabricError)):
                    self._send_json(400, {"error": str(exc)})
                    return
                if isinstance(exc, NotFoundError):
                    self._send_json(404, {"error": str(exc)})
                    return
                self._send_json(500, {"error": str(exc)})

            def log_message(self, format: str, *args) -> None:  # noqa: A003
                return

        return Handler

    def run(self, *, host: str = "127.0.0.1", port: int = 8080) -> None:
        handler = self.build_handler()
        server = ThreadingHTTPServer((host, port), handler)
        server.serve_forever()
