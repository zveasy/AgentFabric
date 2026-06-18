"""Persistent repositories backed by SqliteStore."""

from __future__ import annotations

import base64
import json
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

from agentfabric.errors import AuthorizationError, ConflictError, NotFoundError
from agentfabric.phase2.models import AgentPackage, InstallRecord, MeterEvent, Rating
from agentfabric.production.db import SqliteStore, utc_now_iso


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class ProductionStore:
    """High-level persistent operations across platform domains."""

    def __init__(self, db_path: str = "agentfabric.db") -> None:
        self.db = SqliteStore(db_path=db_path)

    # Registry and install operations
    def put_package(self, package: AgentPackage) -> None:
        row = asdict(package)
        row["created_at"] = package.created_at.isoformat()
        try:
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO registry_packages (
                        namespace, package_id, version, developer_id, category,
                        permissions_json, manifest_json, payload_digest, signature, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        package.namespace,
                        package.package_id,
                        package.version,
                        package.developer_id,
                        package.category,
                        json.dumps(list(package.permissions)),
                        json.dumps(package.manifest, sort_keys=True),
                        package.payload_digest,
                        package.signature,
                        row["created_at"],
                    ),
                )
        except Exception as exc:  # pragma: no cover
            if "UNIQUE constraint failed" in str(exc):
                raise ConflictError("package version already exists") from exc
            raise

    def list_latest_packages(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        required_permissions: set[str] | None = None,
    ) -> list[AgentPackage]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT rp.* FROM registry_packages rp
                INNER JOIN (
                    SELECT namespace, package_id, MAX(created_at) AS max_created
                    FROM registry_packages
                    GROUP BY namespace, package_id
                ) latest
                ON latest.namespace = rp.namespace
                AND latest.package_id = rp.package_id
                AND latest.max_created = rp.created_at
                """
            ).fetchall()
        packages = [self._row_to_package(row) for row in rows]
        result: list[AgentPackage] = []
        for package in packages:
            if query and query.lower() not in package.package_id.lower():
                continue
            if category and package.category != category:
                continue
            if required_permissions and not required_permissions.issubset(set(package.permissions)):
                continue
            result.append(package)
        return result

    def get_package(self, namespace: str, package_id: str, version: str | None = None) -> AgentPackage:
        with self.db.connect() as conn:
            if version is None:
                row = conn.execute(
                    """
                    SELECT * FROM registry_packages
                    WHERE namespace=? AND package_id=?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (namespace, package_id),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM registry_packages
                    WHERE namespace=? AND package_id=? AND version=?
                    """,
                    (namespace, package_id, version),
                ).fetchone()
        if row is None:
            raise NotFoundError("package not found")
        return self._row_to_package(row)

    def add_install(self, tenant_id: str, user_id: str, package_fqid: str) -> InstallRecord:
        installed_at = _now()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO installs (tenant_id, user_id, package_fqid, installed_at)
                VALUES (?, ?, ?, ?)
                """,
                (tenant_id, user_id, package_fqid, installed_at.isoformat()),
            )
        return InstallRecord(tenant_id=tenant_id, user_id=user_id, package_fqid=package_fqid, installed_at=installed_at)

    def list_installs(self, tenant_id: str) -> list[InstallRecord]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM installs WHERE tenant_id=? ORDER BY id", (tenant_id,)).fetchall()
        return [
            InstallRecord(
                tenant_id=row["tenant_id"],
                user_id=row["user_id"],
                package_fqid=row["package_fqid"],
                installed_at=datetime.fromisoformat(row["installed_at"]),
            )
            for row in rows
        ]

    # Billing and settlement
    def record_billing_event(self, event: MeterEvent) -> bool:
        try:
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO billing_events (idempotency_key, event_type, tenant_id, actor_id, package_fqid, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.idempotency_key,
                        event.event_type,
                        event.tenant_id,
                        event.actor_id,
                        event.package_fqid,
                        event.created_at.isoformat(),
                    ),
                )
        except Exception as exc:  # pragma: no cover
            if "UNIQUE constraint failed" in str(exc):
                return False
            raise
        return True

    def usage_counts(self, tenant_id: str) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT event_type, COUNT(*) AS qty FROM billing_events WHERE tenant_id=? GROUP BY event_type",
                (tenant_id,),
            ).fetchall()
        return {row["event_type"]: int(row["qty"]) for row in rows}

    def add_billing_ledger_line(self, tenant_id: str, event_type: str, quantity: int, unit_price: float) -> None:
        subtotal = round(quantity * unit_price, 4)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO billing_ledger (tenant_id, event_type, quantity, unit_price, subtotal, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (tenant_id, event_type, quantity, unit_price, subtotal, utc_now_iso()),
            )

    # Runtime install state persistence
    def upsert_runtime_agent(
        self,
        *,
        agent_id: str,
        manifest: dict[str, Any],
        payload: bytes,
        signature: str,
        signer_id: str,
        signer_key: str,
        state: str,
    ) -> None:
        created_at = utc_now_iso()
        updated_at = utc_now_iso()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO runtime_agents (
                    agent_id, manifest_json, package_payload_b64, signature, signer_id, signer_key, state, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    manifest_json=excluded.manifest_json,
                    package_payload_b64=excluded.package_payload_b64,
                    signature=excluded.signature,
                    signer_id=excluded.signer_id,
                    signer_key=excluded.signer_key,
                    state=excluded.state,
                    updated_at=excluded.updated_at
                """,
                (
                    agent_id,
                    json.dumps(manifest, sort_keys=True),
                    base64.b64encode(payload).decode("utf-8"),
                    signature,
                    signer_id,
                    signer_key,
                    state,
                    created_at,
                    updated_at,
                ),
            )

    def list_runtime_agents(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM runtime_agents ORDER BY agent_id").fetchall()
        out = []
        for row in rows:
            out.append(
                {
                    "agent_id": row["agent_id"],
                    "manifest": json.loads(row["manifest_json"]),
                    "payload": base64.b64decode(row["package_payload_b64"].encode("utf-8")),
                    "signature": row["signature"],
                    "signer_id": row["signer_id"],
                    "signer_key": row["signer_key"],
                    "state": row["state"],
                }
            )
        return out

    def update_runtime_agent_state(self, agent_id: str, state: str) -> None:
        with self.db.connect() as conn:
            updated = conn.execute(
                "UPDATE runtime_agents SET state=?, updated_at=? WHERE agent_id=?",
                (state, utc_now_iso(), agent_id),
            ).rowcount
        if updated == 0:
            raise NotFoundError("runtime agent not found")

    def delete_runtime_agent(self, agent_id: str) -> None:
        with self.db.connect() as conn:
            deleted = conn.execute("DELETE FROM runtime_agents WHERE agent_id=?", (agent_id,)).rowcount
        if deleted == 0:
            raise NotFoundError("runtime agent not found")

    # Auth/token operations
    def upsert_principal(self, principal_id: str, tenant_id: str, principal_type: str, scopes: list[str]) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO auth_principals (principal_id, tenant_id, principal_type, scopes_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(principal_id) DO UPDATE SET
                    tenant_id=excluded.tenant_id,
                    principal_type=excluded.principal_type,
                    scopes_json=excluded.scopes_json
                """,
                (principal_id, tenant_id, principal_type, json.dumps(scopes), utc_now_iso()),
            )

    def get_principal(self, principal_id: str) -> dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM auth_principals WHERE principal_id=?", (principal_id,)).fetchone()
        if row is None:
            raise NotFoundError("principal not found")
        return {
            "principal_id": row["principal_id"],
            "tenant_id": row["tenant_id"],
            "principal_type": row["principal_type"],
            "scopes": json.loads(row["scopes_json"]),
        }

    def store_token(self, token_id: str, principal_id: str, token_hash: str, expires_at: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO auth_tokens (token_id, principal_id, token_hash, expires_at, revoked, issued_at)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (token_id, principal_id, token_hash, expires_at, utc_now_iso()),
            )

    def get_token(self, token_id: str) -> dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM auth_tokens WHERE token_id=?", (token_id,)).fetchone()
        if row is None:
            raise NotFoundError("token not found")
        return {
            "token_id": row["token_id"],
            "principal_id": row["principal_id"],
            "token_hash": row["token_hash"],
            "expires_at": row["expires_at"],
            "revoked": bool(row["revoked"]),
        }

    def revoke_token(self, token_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute("UPDATE auth_tokens SET revoked=1 WHERE token_id=?", (token_id,))

    def register_service_identity(self, service_id: str, tenant_id: str, secret_hash: str, scopes: list[str]) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO service_identities (service_id, tenant_id, secret_hash, scopes_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(service_id) DO UPDATE SET
                    tenant_id=excluded.tenant_id,
                    secret_hash=excluded.secret_hash,
                    scopes_json=excluded.scopes_json
                """,
                (service_id, tenant_id, secret_hash, json.dumps(scopes), utc_now_iso()),
            )

    def get_service_identity(self, service_id: str) -> dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM service_identities WHERE service_id=?", (service_id,)).fetchone()
        if row is None:
            raise NotFoundError("service identity not found")
        return {
            "service_id": row["service_id"],
            "tenant_id": row["tenant_id"],
            "secret_hash": row["secret_hash"],
            "scopes": json.loads(row["scopes_json"]),
        }

    # Enterprise controls
    def assign_role(self, principal_id: str, role: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO enterprise_roles (principal_id, role, created_at) VALUES (?, ?, ?)",
                (principal_id, role, utc_now_iso()),
            )

    def get_roles(self, principal_id: str) -> set[str]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT role FROM enterprise_roles WHERE principal_id=?", (principal_id,)).fetchall()
        return {row["role"] for row in rows}

    def create_namespace(self, tenant_id: str, namespace: str) -> None:
        try:
            with self.db.connect() as conn:
                conn.execute(
                    "INSERT INTO private_namespaces (namespace, owner_tenant_id, created_at) VALUES (?, ?, ?)",
                    (namespace, tenant_id, utc_now_iso()),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO private_namespace_memberships (namespace, tenant_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (namespace, tenant_id, utc_now_iso()),
                )
        except Exception as exc:  # pragma: no cover
            if "UNIQUE constraint failed" in str(exc):
                raise ConflictError("namespace already exists") from exc
            raise

    def grant_namespace_access(self, owner_tenant_id: str, namespace: str, target_tenant_id: str) -> None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT owner_tenant_id FROM private_namespaces WHERE namespace=?",
                (namespace,),
            ).fetchone()
            if row is None:
                raise NotFoundError("namespace not found")
            if row["owner_tenant_id"] != owner_tenant_id:
                raise AuthorizationError("only namespace owner can grant access")
            conn.execute(
                "INSERT OR IGNORE INTO private_namespace_memberships (namespace, tenant_id, created_at) VALUES (?, ?, ?)",
                (namespace, target_tenant_id, utc_now_iso()),
            )

    def has_namespace_access(self, tenant_id: str, namespace: str) -> bool:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM private_namespace_memberships WHERE namespace=? AND tenant_id=?",
                (namespace, tenant_id),
            ).fetchone()
        return row is not None

    def append_audit(
        self,
        *,
        actor_id: str,
        action: str,
        target: str,
        metadata: dict[str, Any],
        previous_hash: str,
        event_hash: str,
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO immutable_audit_events (
                    timestamp, actor_id, action, target, metadata_json, previous_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (utc_now_iso(), actor_id, action, target, json.dumps(metadata, sort_keys=True), previous_hash, event_hash),
            )

    def last_audit_hash(self) -> str:
        with self.db.connect() as conn:
            row = conn.execute("SELECT event_hash FROM immutable_audit_events ORDER BY id DESC LIMIT 1").fetchone()
        return row["event_hash"] if row else "GENESIS"

    def audit_events(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM immutable_audit_events ORDER BY id").fetchall()
        return [
            {
                "timestamp": row["timestamp"],
                "actor_id": row["actor_id"],
                "action": row["action"],
                "target": row["target"],
                "metadata": json.loads(row["metadata_json"]),
                "previous_hash": row["previous_hash"],
                "event_hash": row["event_hash"],
            }
            for row in rows
        ]

    # P2 moderation/compliance/legal
    def submit_review(self, rating: Rating, status: str) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reviews (tenant_id, package_fqid, user_id, stars, review, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (rating.tenant_id, rating.package_fqid, rating.user_id, rating.stars, rating.review, status, rating.created_at.isoformat()),
            )
        return int(cursor.lastrowid)

    def enqueue_review_moderation(self, review_id: int, reason: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO moderation_queue (review_id, status, reason, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (review_id, "pending", reason, utc_now_iso()),
            )

    def pending_reviews(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.*, m.reason
                FROM moderation_queue m
                INNER JOIN reviews r ON r.id = m.review_id
                WHERE m.status='pending'
                ORDER BY r.id
                """
            ).fetchall()
        return [
            {
                "review_id": int(row["id"]),
                "tenant_id": row["tenant_id"],
                "package_fqid": row["package_fqid"],
                "user_id": row["user_id"],
                "stars": int(row["stars"]),
                "review": row["review"],
                "reason": row["reason"],
            }
            for row in rows
        ]

    def moderate_review(self, review_id: int, approved: bool) -> None:
        with self.db.connect() as conn:
            status = "approved" if approved else "rejected"
            conn.execute("UPDATE reviews SET status=? WHERE id=?", (status, review_id))
            conn.execute(
                "UPDATE moderation_queue SET status=?, updated_at=? WHERE review_id=?",
                ("done", utc_now_iso(), review_id),
            )

    def create_deletion_request(self, tenant_id: str, user_id: str | None, reason: str) -> str:
        request_id = f"gdpr-{uuid4()}"
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO gdpr_deletion_requests (request_id, tenant_id, user_id, status, reason, created_at, completed_at)
                VALUES (?, ?, ?, 'pending', ?, ?, NULL)
                """,
                (request_id, tenant_id, user_id, reason, utc_now_iso()),
            )
        return request_id

    def pending_deletion_requests(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM gdpr_deletion_requests WHERE status='pending' ORDER BY created_at"
            ).fetchall()
        return [
            {
                "request_id": row["request_id"],
                "tenant_id": row["tenant_id"],
                "user_id": row["user_id"],
                "reason": row["reason"],
            }
            for row in rows
        ]

    def execute_deletion_request(self, request_id: str) -> None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM gdpr_deletion_requests WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError("deletion request not found")
            tenant_id = row["tenant_id"]
            user_id = row["user_id"]
            if user_id:
                conn.execute("DELETE FROM installs WHERE tenant_id=? AND user_id=?", (tenant_id, user_id))
                conn.execute("DELETE FROM reviews WHERE tenant_id=? AND user_id=?", (tenant_id, user_id))
            else:
                conn.execute("DELETE FROM installs WHERE tenant_id=?", (tenant_id,))
                conn.execute("DELETE FROM reviews WHERE tenant_id=?", (tenant_id,))
            conn.execute(
                """
                UPDATE gdpr_deletion_requests
                SET status='completed', completed_at=?
                WHERE request_id=?
                """,
                (utc_now_iso(), request_id),
            )

    def set_legal_document(self, doc_type: str, version: str, content: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO legal_documents (doc_type, version, content, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(doc_type) DO UPDATE SET
                    version=excluded.version,
                    content=excluded.content,
                    updated_at=excluded.updated_at
                """,
                (doc_type, version, content, utc_now_iso()),
            )

    def get_legal_document(self, doc_type: str) -> dict[str, str]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM legal_documents WHERE doc_type=?",
                (doc_type,),
            ).fetchone()
        if row is None:
            raise NotFoundError("legal document not found")
        return {"doc_type": row["doc_type"], "version": row["version"], "content": row["content"]}

    def accept_legal_document(self, doc_type: str, version: str, principal_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO legal_acceptances (doc_type, version, principal_id, accepted_at)
                VALUES (?, ?, ?, ?)
                """,
                (doc_type, version, principal_id, utc_now_iso()),
            )

    # Utility
    @staticmethod
    def hash_secret(secret: str) -> str:
        return sha256(secret.encode("utf-8")).hexdigest()

    def _row_to_package(self, row: Any) -> AgentPackage:
        return AgentPackage(
            package_id=row["package_id"],
            version=row["version"],
            developer_id=row["developer_id"],
            namespace=row["namespace"],
            category=row["category"],
            permissions=tuple(json.loads(row["permissions_json"])),
            manifest=json.loads(row["manifest_json"]),
            payload_digest=row["payload_digest"],
            signature=row["signature"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
