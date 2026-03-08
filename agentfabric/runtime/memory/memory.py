"""
Memory layer: persistent, scoped storage (per user/session/agent) with
clear retention and isolation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import threading


class MemoryStore:
    """
    Scoped key-value store for agent state. Backed by a directory;
    each scope (user_id, session_id, agent_id) gets an isolated namespace.
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, user_id: str, session_id: str, agent_id: str, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in f"{user_id}_{session_id}_{agent_id}")
        dir_path = self._root / safe
        dir_path.mkdir(parents=True, exist_ok=True)
        key_safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        return dir_path / f"{key_safe}.json"

    def get(
        self,
        user_id: str,
        session_id: str,
        agent_id: str,
        key: str,
    ) -> Any | None:
        """Return stored value or None."""
        p = self._path(user_id, session_id, agent_id, key)
        with self._lock:
            if not p.exists():
                return None
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None

    def set(
        self,
        user_id: str,
        session_id: str,
        agent_id: str,
        key: str,
        value: Any,
    ) -> None:
        """Store a JSON-serializable value."""
        p = self._path(user_id, session_id, agent_id, key)
        with self._lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(value), encoding="utf-8")

    def delete(
        self,
        user_id: str,
        session_id: str,
        agent_id: str,
        key: str,
    ) -> bool:
        """Remove a key. Returns True if it existed."""
        p = self._path(user_id, session_id, agent_id, key)
        with self._lock:
            if p.exists():
                p.unlink()
                return True
            return False

    def clear_session(self, user_id: str, session_id: str, agent_id: str) -> None:
        """Remove all keys for a given scope."""
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in f"{user_id}_{session_id}_{agent_id}")
        dir_path = self._root / safe
        with self._lock:
            if dir_path.exists():
                for f in dir_path.iterdir():
                    if f.suffix == ".json":
                        f.unlink()
