"""Persistent scoped memory storage with retention controls."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class MemoryScope:
    user_id: str
    session_id: str
    agent_id: str

    def key_prefix(self) -> str:
        return f"{self.user_id}:{self.session_id}:{self.agent_id}"


class ScopedMemoryStore:
    """JSON-backed memory store scoped by user/session/agent."""

    def __init__(self, storage_file: str = ".agentfabric_memory.json") -> None:
        self._storage_file = Path(storage_file)
        self._records: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self._storage_file.exists():
            self._records = json.loads(self._storage_file.read_text(encoding="utf-8"))

    def _persist(self) -> None:
        self._storage_file.write_text(json.dumps(self._records, sort_keys=True), encoding="utf-8")

    def set(self, scope: MemoryScope, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        expires_at: str | None = None
        if ttl_seconds is not None:
            expires_at = (utc_now() + timedelta(seconds=ttl_seconds)).isoformat()
        self._records[f"{scope.key_prefix()}:{key}"] = {"value": value, "expires_at": expires_at}
        self._persist()

    def get(self, scope: MemoryScope, key: str) -> Any | None:
        composite = f"{scope.key_prefix()}:{key}"
        item = self._records.get(composite)
        if item is None:
            return None
        expires_at = item["expires_at"]
        if expires_at and datetime.fromisoformat(expires_at) <= utc_now():
            del self._records[composite]
            self._persist()
            return None
        return item["value"]

    def purge_expired(self) -> int:
        now = utc_now()
        removed = 0
        for key in list(self._records.keys()):
            expires_at = self._records[key]["expires_at"]
            if expires_at and datetime.fromisoformat(expires_at) <= now:
                del self._records[key]
                removed += 1
        if removed:
            self._persist()
        return removed
