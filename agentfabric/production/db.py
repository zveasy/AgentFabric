"""SQLite-backed persistence primitives for production services."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS registry_packages (
    namespace TEXT NOT NULL,
    package_id TEXT NOT NULL,
    version TEXT NOT NULL,
    developer_id TEXT NOT NULL,
    category TEXT NOT NULL,
    permissions_json TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    signature TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(namespace, package_id, version)
);

CREATE TABLE IF NOT EXISTS installs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    package_fqid TEXT NOT NULL,
    installed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS billing_events (
    idempotency_key TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    package_fqid TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS billing_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    subtotal REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_agents (
    agent_id TEXT PRIMARY KEY,
    manifest_json TEXT NOT NULL,
    package_payload_b64 TEXT NOT NULL,
    signature TEXT NOT NULL,
    signer_id TEXT NOT NULL,
    signer_key TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_principals (
    principal_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    principal_type TEXT NOT NULL,
    scopes_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token_id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    issued_at TEXT NOT NULL,
    FOREIGN KEY(principal_id) REFERENCES auth_principals(principal_id)
);

CREATE TABLE IF NOT EXISTS service_identities (
    service_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    secret_hash TEXT NOT NULL,
    scopes_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS enterprise_roles (
    principal_id TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(principal_id, role)
);

CREATE TABLE IF NOT EXISTS private_namespaces (
    namespace TEXT PRIMARY KEY,
    owner_tenant_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS private_namespace_memberships (
    namespace TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(namespace, tenant_id)
);

CREATE TABLE IF NOT EXISTS immutable_audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    package_fqid TEXT NOT NULL,
    user_id TEXT NOT NULL,
    stars INTEGER NOT NULL,
    review TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS moderation_queue (
    review_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL,
    reason TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gdpr_deletion_requests (
    request_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS legal_documents (
    doc_type TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    content TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS legal_acceptances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type TEXT NOT NULL,
    version TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    accepted_at TEXT NOT NULL
);
"""


class SqliteStore:
    """Connection manager and schema bootstrap for persistent data."""

    def __init__(self, db_path: str = "agentfabric.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
