"""Database-backed persistence primitives for production services."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import Boolean, Column, Float, Integer, MetaData, String, Table, Text, create_engine
from sqlalchemy.engine import Connection

def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


METADATA = MetaData()

Table(
    "registry_packages",
    METADATA,
    Column("namespace", String(256), primary_key=True),
    Column("package_id", String(256), primary_key=True),
    Column("version", String(64), primary_key=True),
    Column("developer_id", String(256), nullable=False),
    Column("category", String(128), nullable=False),
    Column("permissions_json", Text, nullable=False),
    Column("manifest_json", Text, nullable=False),
    Column("payload_digest", String(128), nullable=False),
    Column("signature", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
)

Table(
    "installs",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String(128), nullable=False),
    Column("user_id", String(128), nullable=False),
    Column("package_fqid", String(512), nullable=False),
    Column("created_at", String(64), nullable=False),
)

Table(
    "billing_events",
    METADATA,
    Column("idempotency_key", String(256), primary_key=True),
    Column("event_type", String(64), nullable=False),
    Column("tenant_id", String(128), nullable=False),
    Column("actor_id", String(128), nullable=False),
    Column("package_fqid", String(512), nullable=False),
    Column("created_at", String(64), nullable=False),
)

Table(
    "billing_ledger",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String(128), nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("unit_price", Float, nullable=False),
    Column("subtotal", Float, nullable=False),
    Column("created_at", String(64), nullable=False),
)

Table(
    "runtime_agents",
    METADATA,
    Column("agent_id", String(256), primary_key=True),
    Column("manifest_json", Text, nullable=False),
    Column("package_payload_b64", Text, nullable=False),
    Column("signature", Text, nullable=False),
    Column("signer_id", String(256), nullable=False),
    Column("signer_key", String(256), nullable=False),
    Column("state", String(32), nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
)

Table(
    "auth_principals",
    METADATA,
    Column("principal_id", String(128), primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column("principal_type", String(32), nullable=False),
    Column("scopes_json", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
)

Table(
    "auth_tokens",
    METADATA,
    Column("token_id", String(128), primary_key=True),
    Column("principal_id", String(128), nullable=False),
    Column("token_hash", String(256), nullable=False),
    Column("expires_at", String(64), nullable=False),
    Column("revoked", Boolean, nullable=False, default=False),
    Column("issued_at", String(64), nullable=False),
)

Table(
    "service_identities",
    METADATA,
    Column("service_id", String(128), primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column("secret_hash", String(256), nullable=False),
    Column("scopes_json", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
)

Table(
    "enterprise_roles",
    METADATA,
    Column("principal_id", String(128), primary_key=True),
    Column("role", String(64), primary_key=True),
    Column("created_at", String(64), nullable=False),
)

Table(
    "private_namespaces",
    METADATA,
    Column("namespace", String(256), primary_key=True),
    Column("owner_tenant_id", String(128), nullable=False),
    Column("created_at", String(64), nullable=False),
)

Table(
    "private_namespace_memberships",
    METADATA,
    Column("namespace", String(256), primary_key=True),
    Column("tenant_id", String(128), primary_key=True),
    Column("created_at", String(64), nullable=False),
)

Table(
    "immutable_audit_events",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", String(64), nullable=False),
    Column("actor_id", String(128), nullable=False),
    Column("action", String(128), nullable=False),
    Column("target", String(256), nullable=False),
    Column("metadata_json", Text, nullable=False),
    Column("previous_hash", String(128), nullable=False),
    Column("event_hash", String(128), nullable=False),
)

Table(
    "reviews",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String(128), nullable=False),
    Column("package_fqid", String(512), nullable=False),
    Column("user_id", String(128), nullable=False),
    Column("stars", Integer, nullable=False),
    Column("review", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_at", String(64), nullable=False),
)

Table(
    "moderation_queue",
    METADATA,
    Column("review_id", Integer, primary_key=True),
    Column("status", String(32), nullable=False),
    Column("reason", String(512), nullable=True),
    Column("updated_at", String(64), nullable=False),
)

Table(
    "gdpr_deletion_requests",
    METADATA,
    Column("request_id", String(128), primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column("user_id", String(128), nullable=True),
    Column("status", String(32), nullable=False),
    Column("reason", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("completed_at", String(64), nullable=True),
)

Table(
    "legal_documents",
    METADATA,
    Column("doc_type", String(64), primary_key=True),
    Column("version", String(64), nullable=False),
    Column("content", Text, nullable=False),
    Column("updated_at", String(64), nullable=False),
)

Table(
    "legal_acceptances",
    METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("doc_type", String(64), nullable=False),
    Column("version", String(64), nullable=False),
    Column("principal_id", String(128), nullable=False),
    Column("accepted_at", String(64), nullable=False),
)


class SqlStore:
    """Connection manager and schema bootstrap for persistence data."""

    def __init__(self, *, database_url: str | None = None, db_path: str = "agentfabric.db") -> None:
        self.database_url = database_url or f"sqlite:///{db_path}"
        connect_args = {"check_same_thread": False} if self.database_url.startswith("sqlite") else {}
        self._engine = create_engine(self.database_url, future=True, pool_pre_ping=True, connect_args=connect_args)
        self.db_path: Path | None = self._sqlite_path_from_url(self.database_url)
        if self.db_path is not None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @staticmethod
    def _sqlite_path_from_url(database_url: str) -> Path | None:
        prefix = "sqlite:///"
        if not database_url.startswith(prefix):
            return None
        return Path(database_url[len(prefix) :])

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        with self._engine.begin() as conn:
            yield conn

    def _init_schema(self) -> None:
        METADATA.create_all(self._engine, checkfirst=True)
