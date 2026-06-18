"""
Audit logging: log installs, runs, permission denials, and sandbox events.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO
import threading


class AuditLog:
    """
    Append-only audit log for security-relevant events.
    Writes JSON lines to a file or stream.
    """

    def __init__(self, path: Path | str | None = None, stream: TextIO | None = None) -> None:
        self._path = Path(path) if path else None
        self._stream = stream
        self._lock = threading.Lock()
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, default=str) + "\n"
        with self._lock:
            if self._stream:
                self._stream.write(line)
                self._stream.flush()
            if self._path:
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(line)

    def log_install(self, agent_id: str, version: str, path: str, success: bool) -> None:
        self._write({
            "event": "install",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
            "version": version,
            "path": path,
            "success": success,
        })

    def log_uninstall(self, agent_id: str) -> None:
        self._write({
            "event": "uninstall",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
        })

    def log_run_start(self, request_id: str, agent_id: str, correlation_id: str) -> None:
        self._write({
            "event": "run_started",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "agent_id": agent_id,
            "correlation_id": correlation_id,
        })

    def log_run_end(self, request_id: str, agent_id: str, success: bool) -> None:
        self._write({
            "event": "run_completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "agent_id": agent_id,
            "success": success,
        })

    def log_permission_denied(self, request_id: str, agent_id: str, tool_or_resource: str, reason: str) -> None:
        self._write({
            "event": "permission_denied",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "agent_id": agent_id,
            "tool_or_resource": tool_or_resource,
            "reason": reason,
        })

    def log_sandbox_event(self, request_id: str, agent_id: str, kind: str, detail: dict[str, Any] | None = None) -> None:
        self._write({
            "event": "sandbox_event",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "agent_id": agent_id,
            "kind": kind,
            "detail": detail or {},
        })
