"""SQLite-backed JSON document store."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import sqlite3
from pathlib import Path
from typing import Iterator


class SQLitePersistenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._active_conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS af_documents (
                    collection TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (collection, key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS af_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def put(self, collection: str, key: str, value: dict[str, object]) -> None:
        self.initialize()
        conn = self._active_conn
        if conn is not None:
            conn.execute(
                """
                INSERT INTO af_documents(collection, key, value, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(collection, key)
                DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                (collection, key, json.dumps(value, sort_keys=True)),
            )
            return
        with self._connect() as owned_conn:
            owned_conn.execute(
                """
                INSERT INTO af_documents(collection, key, value, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(collection, key)
                DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                (collection, key, json.dumps(value, sort_keys=True)),
            )

    def get(self, collection: str, key: str) -> dict[str, object] | None:
        self.initialize()
        conn = self._active_conn
        if conn is not None:
            row = conn.execute(
                "SELECT value FROM af_documents WHERE collection = ? AND key = ?",
                (collection, key),
            ).fetchone()
            return deepcopy(json.loads(row["value"])) if row else None
        with self._connect() as owned_conn:
            row = owned_conn.execute(
                "SELECT value FROM af_documents WHERE collection = ? AND key = ?",
                (collection, key),
            ).fetchone()
        return deepcopy(json.loads(row["value"])) if row else None

    def delete(self, collection: str, key: str) -> bool:
        self.initialize()
        conn = self._active_conn
        if conn is not None:
            cursor = conn.execute(
                "DELETE FROM af_documents WHERE collection = ? AND key = ?",
                (collection, key),
            )
            return cursor.rowcount > 0
        with self._connect() as owned_conn:
            cursor = owned_conn.execute(
                "DELETE FROM af_documents WHERE collection = ? AND key = ?",
                (collection, key),
            )
            return cursor.rowcount > 0

    def list(self, collection: str) -> list[dict[str, object]]:
        self.initialize()
        conn = self._active_conn
        if conn is not None:
            rows = conn.execute(
                "SELECT value FROM af_documents WHERE collection = ? ORDER BY key",
                (collection,),
            ).fetchall()
            return [deepcopy(json.loads(row["value"])) for row in rows]
        with self._connect() as owned_conn:
            rows = owned_conn.execute(
                "SELECT value FROM af_documents WHERE collection = ? ORDER BY key",
                (collection,),
            ).fetchall()
        return [deepcopy(json.loads(row["value"])) for row in rows]

    def list_tenant(self, collection: str, tenant_id: str) -> list[dict[str, object]]:
        return [item for item in self.list(collection) if item.get("tenant_id") == tenant_id]

    def keys(self, collection: str) -> list[str]:
        self.initialize()
        conn = self._active_conn
        if conn is not None:
            rows = conn.execute(
                "SELECT key FROM af_documents WHERE collection = ? ORDER BY key",
                (collection,),
            ).fetchall()
            return [str(row["key"]) for row in rows]
        with self._connect() as owned_conn:
            rows = owned_conn.execute(
                "SELECT key FROM af_documents WHERE collection = ? ORDER BY key",
                (collection,),
            ).fetchall()
        return [str(row["key"]) for row in rows]

    def health(self) -> dict[str, object]:
        try:
            self.initialize()
            with self._connect() as conn:
                count = conn.execute("SELECT COUNT(*) AS count FROM af_documents").fetchone()["count"]
            return {"status": "ok", "backend": "sqlite", "documents": count}
        except Exception as exc:
            return {"status": "error", "backend": "sqlite", "error": str(exc)}

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.initialize()
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN")
            self._active_conn = conn
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._active_conn = None
            conn.close()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
