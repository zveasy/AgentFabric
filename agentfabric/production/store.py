"""Persistent repositories backed by SqlStore."""

from __future__ import annotations

import base64
import json
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from agentfabric.errors import AuthorizationError, ConflictError, NotFoundError
from agentfabric.phase2.models import AgentPackage, InstallRecord, MeterEvent, Rating
from agentfabric.production.db import SqlStore, utc_now_iso


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class ProductionStore:
    """High-level persistent operations across platform domains."""

    def __init__(self, db_path: str = "agentfabric.db", *, database_url: str | None = None) -> None:
        self.db = SqlStore(database_url=database_url, db_path=db_path)

    def backup_source_path(self) -> str | None:
        if self.db.db_path is None:
            return None
        return str(self.db.db_path)

    # Registry and install operations
    def put_package(self, package: AgentPackage) -> None:
        row = asdict(package)
        row["created_at"] = package.created_at.isoformat()
        try:
            with self.db.connect() as conn:
                conn.execute(
                    text(
                        """
                    INSERT INTO registry_packages (
                        namespace, package_id, version, developer_id, category,
                        permissions_json, manifest_json, payload_digest, signature, created_at
                    ) VALUES (
                        :namespace, :package_id, :version, :developer_id, :category,
                        :permissions_json, :manifest_json, :payload_digest, :signature, :created_at
                    )
                    """
                    ),
                    {
                        "namespace": package.namespace,
                        "package_id": package.package_id,
                        "version": package.version,
                        "developer_id": package.developer_id,
                        "category": package.category,
                        "permissions_json": json.dumps(list(package.permissions)),
                        "manifest_json": json.dumps(package.manifest, sort_keys=True),
                        "payload_digest": package.payload_digest,
                        "signature": package.signature,
                        "created_at": row["created_at"],
                    },
                )
        except IntegrityError as exc:  # pragma: no cover
            if "unique" in str(exc).lower():
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
                text(
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
                )
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
                    text(
                        """
                    SELECT * FROM registry_packages
                    WHERE namespace=:namespace AND package_id=:package_id
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                    ),
                    {"namespace": namespace, "package_id": package_id},
                ).fetchone()
            else:
                row = conn.execute(
                    text(
                        """
                    SELECT * FROM registry_packages
                    WHERE namespace=:namespace AND package_id=:package_id AND version=:version
                    """
                    ),
                    {"namespace": namespace, "package_id": package_id, "version": version},
                ).fetchone()
        if row is None:
            raise NotFoundError("package not found")
        return self._row_to_package(row)

    def add_install(self, tenant_id: str, user_id: str, package_fqid: str) -> InstallRecord:
        installed_at = _now()
        with self.db.connect() as conn:
            conn.execute(
                text(
                    """
                INSERT INTO installs (tenant_id, user_id, package_fqid, created_at)
                VALUES (:tenant_id, :user_id, :package_fqid, :created_at)
                """
                ),
                {
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "package_fqid": package_fqid,
                    "created_at": installed_at.isoformat(),
                },
            )
        return InstallRecord(tenant_id=tenant_id, user_id=user_id, package_fqid=package_fqid, installed_at=installed_at)

    def list_installs(self, tenant_id: str) -> list[InstallRecord]:
        with self.db.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM installs WHERE tenant_id=:tenant_id ORDER BY id"),
                {"tenant_id": tenant_id},
            ).fetchall()
        return [
            InstallRecord(
                tenant_id=row._mapping["tenant_id"],
                user_id=row._mapping["user_id"],
                package_fqid=row._mapping["package_fqid"],
                installed_at=datetime.fromisoformat(row._mapping["created_at"]),
            )
            for row in rows
        ]

    # Billing and settlement
    def record_billing_event(self, event: MeterEvent) -> bool:
        try:
            with self.db.connect() as conn:
                conn.execute(
                    text(
                        """
                    INSERT INTO billing_events (idempotency_key, event_type, tenant_id, actor_id, package_fqid, created_at)
                    VALUES (:idempotency_key, :event_type, :tenant_id, :actor_id, :package_fqid, :created_at)
                    """
                    ),
                    {
                        "idempotency_key": event.idempotency_key,
                        "event_type": event.event_type,
                        "tenant_id": event.tenant_id,
                        "actor_id": event.actor_id,
                        "package_fqid": event.package_fqid,
                        "created_at": event.created_at.isoformat(),
                    },
                )
        except IntegrityError as exc:  # pragma: no cover
            if "unique" in str(exc).lower():
                return False
            raise
        return True

    def usage_counts(self, tenant_id: str) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                text("SELECT event_type, COUNT(*) AS qty FROM billing_events WHERE tenant_id=:tenant_id GROUP BY event_type"),
                {"tenant_id": tenant_id},
            ).fetchall()
        return {row._mapping["event_type"]: int(row._mapping["qty"]) for row in rows}

    def add_billing_ledger_line(self, tenant_id: str, event_type: str, quantity: int, unit_price: float) -> None:
        subtotal = round(quantity * unit_price, 4)
        with self.db.connect() as conn:
            conn.execute(
                text(
                    """
                INSERT INTO billing_ledger (tenant_id, event_type, quantity, unit_price, subtotal, created_at)
                VALUES (:tenant_id, :event_type, :quantity, :unit_price, :subtotal, :created_at)
                """
                ),
                {
                    "tenant_id": tenant_id,
                    "event_type": event_type,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "subtotal": subtotal,
                    "created_at": utc_now_iso(),
                },
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
                text(
                    """
                INSERT INTO runtime_agents (
                    agent_id, manifest_json, package_payload_b64, signature, signer_id, signer_key, state, created_at, updated_at
                ) VALUES (
                    :agent_id, :manifest_json, :package_payload_b64, :signature, :signer_id, :signer_key, :state, :created_at, :updated_at
                )
                ON CONFLICT(agent_id) DO UPDATE SET
                    manifest_json=excluded.manifest_json,
                    package_payload_b64=excluded.package_payload_b64,
                    signature=excluded.signature,
                    signer_id=excluded.signer_id,
                    signer_key=excluded.signer_key,
                    state=excluded.state,
                    updated_at=excluded.updated_at
                """
                ),
                {
                    "agent_id": agent_id,
                    "manifest_json": json.dumps(manifest, sort_keys=True),
                    "package_payload_b64": base64.b64encode(payload).decode("utf-8"),
                    "signature": signature,
                    "signer_id": signer_id,
                    "signer_key": signer_key,
                    "state": state,
                    "created_at": created_at,
                    "updated_at": updated_at,
                },
            )

    def list_runtime_agents(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(text("SELECT * FROM runtime_agents ORDER BY agent_id")).fetchall()
        out = []
        for row in rows:
            m = row._mapping
            out.append(
                {
                    "agent_id": m["agent_id"],
                    "manifest": json.loads(m["manifest_json"]),
                    "payload": base64.b64decode(m["package_payload_b64"].encode("utf-8")),
                    "signature": m["signature"],
                    "signer_id": m["signer_id"],
                    "signer_key": m["signer_key"],
                    "state": m["state"],
                }
            )
        return out

    def update_runtime_agent_state(self, agent_id: str, state: str) -> None:
        with self.db.connect() as conn:
            updated = conn.execute(
                text("UPDATE runtime_agents SET state=:state, updated_at=:updated_at WHERE agent_id=:agent_id"),
                {"state": state, "updated_at": utc_now_iso(), "agent_id": agent_id},
            ).rowcount
        if updated == 0:
            raise NotFoundError("runtime agent not found")

    def delete_runtime_agent(self, agent_id: str) -> None:
        with self.db.connect() as conn:
            deleted = conn.execute(
                text("DELETE FROM runtime_agents WHERE agent_id=:agent_id"),
                {"agent_id": agent_id},
            ).rowcount
        if deleted == 0:
            raise NotFoundError("runtime agent not found")

    # Auth/token operations
    def upsert_principal(self, principal_id: str, tenant_id: str, principal_type: str, scopes: list[str]) -> None:
        with self.db.connect() as conn:
            conn.execute(
                text(
                    """
                INSERT INTO auth_principals (principal_id, tenant_id, principal_type, scopes_json, created_at)
                VALUES (:principal_id, :tenant_id, :principal_type, :scopes_json, :created_at)
                ON CONFLICT(principal_id) DO UPDATE SET
                    tenant_id=excluded.tenant_id,
                    principal_type=excluded.principal_type,
                    scopes_json=excluded.scopes_json
                """
                ),
                {
                    "principal_id": principal_id,
                    "tenant_id": tenant_id,
                    "principal_type": principal_type,
                    "scopes_json": json.dumps(scopes),
                    "created_at": utc_now_iso(),
                },
            )

    def get_principal(self, principal_id: str) -> dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM auth_principals WHERE principal_id=:principal_id"),
                {"principal_id": principal_id},
            ).fetchone()
        if row is None:
            raise NotFoundError("principal not found")
        m = row._mapping
        return {
            "principal_id": m["principal_id"],
            "tenant_id": m["tenant_id"],
            "principal_type": m["principal_type"],
            "scopes": json.loads(m["scopes_json"]),
        }

    def store_token(self, token_id: str, principal_id: str, token_hash: str, expires_at: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                text(
                    """
                INSERT INTO auth_tokens (token_id, principal_id, token_hash, expires_at, revoked, issued_at)
                VALUES (:token_id, :principal_id, :token_hash, :expires_at, false, :issued_at)
                """
                ),
                {
                    "token_id": token_id,
                    "principal_id": principal_id,
                    "token_hash": token_hash,
                    "expires_at": expires_at,
                    "issued_at": utc_now_iso(),
                },
            )

    def get_token(self, token_id: str) -> dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM auth_tokens WHERE token_id=:token_id"),
                {"token_id": token_id},
            ).fetchone()
        if row is None:
            raise NotFoundError("token not found")
        m = row._mapping
        return {
            "token_id": m["token_id"],
            "principal_id": m["principal_id"],
            "token_hash": m["token_hash"],
            "expires_at": m["expires_at"],
            "revoked": bool(m["revoked"]),
        }

    def revoke_token(self, token_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                text("UPDATE auth_tokens SET revoked=true WHERE token_id=:token_id"),
                {"token_id": token_id},
            )

    def register_service_identity(self, service_id: str, tenant_id: str, secret_hash: str, scopes: list[str]) -> None:
        with self.db.connect() as conn:
            conn.execute(
                text(
                    """
                INSERT INTO service_identities (service_id, tenant_id, secret_hash, scopes_json, created_at)
                VALUES (:service_id, :tenant_id, :secret_hash, :scopes_json, :created_at)
                ON CONFLICT(service_id) DO UPDATE SET
                    tenant_id=excluded.tenant_id,
                    secret_hash=excluded.secret_hash,
                    scopes_json=excluded.scopes_json
                """
                ),
                {
                    "service_id": service_id,
                    "tenant_id": tenant_id,
                    "secret_hash": secret_hash,
                    "scopes_json": json.dumps(scopes),
                    "created_at": utc_now_iso(),
                },
            )

    def get_service_identity(self, service_id: str) -> dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM service_identities WHERE service_id=:service_id"),
                {"service_id": service_id},
            ).fetchone()
        if row is None:
            raise NotFoundError("service identity not found")
        m = row._mapping
        return {
            "service_id": m["service_id"],
            "tenant_id": m["tenant_id"],
            "secret_hash": m["secret_hash"],
            "scopes": json.loads(m["scopes_json"]),
        }

    # Enterprise controls
    def assign_role(self, principal_id: str, role: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO enterprise_roles (principal_id, role, created_at)
                    VALUES (:principal_id, :role, :created_at)
                    ON CONFLICT(principal_id, role) DO NOTHING
                    """
                ),
                {"principal_id": principal_id, "role": role, "created_at": utc_now_iso()},
            )

    def get_roles(self, principal_id: str) -> set[str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                text("SELECT role FROM enterprise_roles WHERE principal_id=:principal_id"),
                {"principal_id": principal_id},
            ).fetchall()
        return {str(row._mapping["role"]) for row in rows}

    def create_namespace(self, tenant_id: str, namespace: str) -> None:
        try:
            with self.db.connect() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO private_namespaces (namespace, owner_tenant_id, created_at)
                        VALUES (:namespace, :owner_tenant_id, :created_at)
                        """
                    ),
                    {"namespace": namespace, "owner_tenant_id": tenant_id, "created_at": utc_now_iso()},
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO private_namespace_memberships (namespace, tenant_id, created_at)
                        VALUES (:namespace, :tenant_id, :created_at)
                        ON CONFLICT(namespace, tenant_id) DO NOTHING
                        """
                    ),
                    {"namespace": namespace, "tenant_id": tenant_id, "created_at": utc_now_iso()},
                )
        except IntegrityError as exc:  # pragma: no cover
            if "unique" in str(exc).lower():
                raise ConflictError("namespace already exists") from exc
            raise

    def grant_namespace_access(self, owner_tenant_id: str, namespace: str, target_tenant_id: str) -> None:
        with self.db.connect() as conn:
            row = conn.execute(
                text("SELECT owner_tenant_id FROM private_namespaces WHERE namespace=:namespace"),
                {"namespace": namespace},
            ).fetchone()
            if row is None:
                raise NotFoundError("namespace not found")
            if str(row._mapping["owner_tenant_id"]) != owner_tenant_id:
                raise AuthorizationError("only namespace owner can grant access")
            conn.execute(
                text(
                    """
                    INSERT INTO private_namespace_memberships (namespace, tenant_id, created_at)
                    VALUES (:namespace, :tenant_id, :created_at)
                    ON CONFLICT(namespace, tenant_id) DO NOTHING
                    """
                ),
                {"namespace": namespace, "tenant_id": target_tenant_id, "created_at": utc_now_iso()},
            )

    def has_namespace_access(self, tenant_id: str, namespace: str) -> bool:
        with self.db.connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM private_namespace_memberships WHERE namespace=:namespace AND tenant_id=:tenant_id"),
                {"namespace": namespace, "tenant_id": tenant_id},
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
                text(
                    """
                INSERT INTO immutable_audit_events (
                    timestamp, actor_id, action, target, metadata_json, previous_hash, event_hash
                ) VALUES (:timestamp, :actor_id, :action, :target, :metadata_json, :previous_hash, :event_hash)
                """
                ),
                {
                    "timestamp": utc_now_iso(),
                    "actor_id": actor_id,
                    "action": action,
                    "target": target,
                    "metadata_json": json.dumps(metadata, sort_keys=True),
                    "previous_hash": previous_hash,
                    "event_hash": event_hash,
                },
            )

    def last_audit_hash(self) -> str:
        with self.db.connect() as conn:
            row = conn.execute(text("SELECT event_hash FROM immutable_audit_events ORDER BY id DESC LIMIT 1")).fetchone()
        return str(row._mapping["event_hash"]) if row else "GENESIS"

    def audit_events(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(text("SELECT * FROM immutable_audit_events ORDER BY id")).fetchall()
        return [
            {
                "timestamp": row._mapping["timestamp"],
                "actor_id": row._mapping["actor_id"],
                "action": row._mapping["action"],
                "target": row._mapping["target"],
                "metadata": json.loads(row._mapping["metadata_json"]),
                "previous_hash": row._mapping["previous_hash"],
                "event_hash": row._mapping["event_hash"],
            }
            for row in rows
        ]

    # P2 moderation/compliance/legal
    def submit_review(self, rating: Rating, status: str) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute(
                text(
                    """
                INSERT INTO reviews (tenant_id, package_fqid, user_id, stars, review, status, created_at)
                VALUES (:tenant_id, :package_fqid, :user_id, :stars, :review, :status, :created_at)
                RETURNING id
                """
                ),
                {
                    "tenant_id": rating.tenant_id,
                    "package_fqid": rating.package_fqid,
                    "user_id": rating.user_id,
                    "stars": rating.stars,
                    "review": rating.review,
                    "status": status,
                    "created_at": rating.created_at.isoformat(),
                },
            )
            review_id = cursor.scalar_one()
        return int(review_id)

    def enqueue_review_moderation(self, review_id: int, reason: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO moderation_queue (review_id, status, reason, updated_at)
                    VALUES (:review_id, :status, :reason, :updated_at)
                    ON CONFLICT(review_id) DO UPDATE SET
                        status=excluded.status,
                        reason=excluded.reason,
                        updated_at=excluded.updated_at
                    """
                ),
                {"review_id": review_id, "status": "pending", "reason": reason, "updated_at": utc_now_iso()},
            )

    def pending_reviews(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                text(
                    """
                SELECT r.*, m.reason
                FROM moderation_queue m
                INNER JOIN reviews r ON r.id = m.review_id
                WHERE m.status='pending'
                ORDER BY r.id
                """
                )
            ).fetchall()
        return [
            {
                "review_id": int(row._mapping["id"]),
                "tenant_id": row._mapping["tenant_id"],
                "package_fqid": row._mapping["package_fqid"],
                "user_id": row._mapping["user_id"],
                "stars": int(row._mapping["stars"]),
                "review": row._mapping["review"],
                "reason": row._mapping["reason"],
            }
            for row in rows
        ]

    def moderate_review(self, review_id: int, approved: bool) -> None:
        with self.db.connect() as conn:
            status = "approved" if approved else "rejected"
            conn.execute(
                text("UPDATE reviews SET status=:status WHERE id=:review_id"),
                {"status": status, "review_id": review_id},
            )
            conn.execute(
                text("UPDATE moderation_queue SET status=:status, updated_at=:updated_at WHERE review_id=:review_id"),
                {"status": "done", "updated_at": utc_now_iso(), "review_id": review_id},
            )

    def create_deletion_request(self, tenant_id: str, user_id: str | None, reason: str) -> str:
        request_id = f"gdpr-{uuid4()}"
        with self.db.connect() as conn:
            conn.execute(
                text(
                    """
                INSERT INTO gdpr_deletion_requests (request_id, tenant_id, user_id, status, reason, created_at, completed_at)
                VALUES (:request_id, :tenant_id, :user_id, 'pending', :reason, :created_at, NULL)
                """
                ),
                {
                    "request_id": request_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "reason": reason,
                    "created_at": utc_now_iso(),
                },
            )
        return request_id

    def pending_deletion_requests(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM gdpr_deletion_requests WHERE status='pending' ORDER BY created_at")
            ).fetchall()
        return [
            {
                "request_id": row._mapping["request_id"],
                "tenant_id": row._mapping["tenant_id"],
                "user_id": row._mapping["user_id"],
                "reason": row._mapping["reason"],
            }
            for row in rows
        ]

    def execute_deletion_request(self, request_id: str) -> None:
        with self.db.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM gdpr_deletion_requests WHERE request_id=:request_id"),
                {"request_id": request_id},
            ).fetchone()
            if row is None:
                raise NotFoundError("deletion request not found")
            tenant_id = row._mapping["tenant_id"]
            user_id = row._mapping["user_id"]
            if user_id:
                conn.execute(
                    text("DELETE FROM installs WHERE tenant_id=:tenant_id AND user_id=:user_id"),
                    {"tenant_id": tenant_id, "user_id": user_id},
                )
                conn.execute(
                    text("DELETE FROM reviews WHERE tenant_id=:tenant_id AND user_id=:user_id"),
                    {"tenant_id": tenant_id, "user_id": user_id},
                )
            else:
                conn.execute(text("DELETE FROM installs WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
                conn.execute(text("DELETE FROM reviews WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
            conn.execute(
                text(
                    """
                UPDATE gdpr_deletion_requests
                SET status='completed', completed_at=:completed_at
                WHERE request_id=:request_id
                """
                ),
                {"completed_at": utc_now_iso(), "request_id": request_id},
            )

    def set_legal_document(self, doc_type: str, version: str, content: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                text(
                    """
                INSERT INTO legal_documents (doc_type, version, content, updated_at)
                VALUES (:doc_type, :version, :content, :updated_at)
                ON CONFLICT(doc_type) DO UPDATE SET
                    version=excluded.version,
                    content=excluded.content,
                    updated_at=excluded.updated_at
                """
                ),
                {"doc_type": doc_type, "version": version, "content": content, "updated_at": utc_now_iso()},
            )

    def get_legal_document(self, doc_type: str) -> dict[str, str]:
        with self.db.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM legal_documents WHERE doc_type=:doc_type"),
                {"doc_type": doc_type},
            ).fetchone()
        if row is None:
            raise NotFoundError("legal document not found")
        return {
            "doc_type": str(row._mapping["doc_type"]),
            "version": str(row._mapping["version"]),
            "content": str(row._mapping["content"]),
        }

    def accept_legal_document(self, doc_type: str, version: str, principal_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                text(
                    """
                INSERT INTO legal_acceptances (doc_type, version, principal_id, accepted_at)
                VALUES (:doc_type, :version, :principal_id, :accepted_at)
                """
                ),
                {"doc_type": doc_type, "version": version, "principal_id": principal_id, "accepted_at": utc_now_iso()},
            )

    # Utility
    @staticmethod
    def hash_secret(secret: str) -> str:
        return sha256(secret.encode("utf-8")).hexdigest()

    def _row_to_package(self, row: Any) -> AgentPackage:
        m = row._mapping if hasattr(row, "_mapping") else row
        return AgentPackage(
            package_id=m["package_id"],
            version=m["version"],
            developer_id=m["developer_id"],
            namespace=m["namespace"],
            category=m["category"],
            permissions=tuple(json.loads(m["permissions_json"])),
            manifest=json.loads(m["manifest_json"]),
            payload_digest=m["payload_digest"],
            signature=m["signature"],
            created_at=datetime.fromisoformat(m["created_at"]),
        )
