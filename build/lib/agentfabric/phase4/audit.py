"""Immutable audit log using hash chaining."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class AuditEvent:
    timestamp: datetime
    actor_id: str
    action: str
    target: str
    metadata: dict[str, Any]
    previous_hash: str
    event_hash: str


class ImmutableAuditLog:
    """Append-only audit log with integrity verification."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, actor_id: str, action: str, target: str, metadata: dict[str, Any] | None = None) -> AuditEvent:
        metadata = metadata or {}
        previous_hash = self._events[-1].event_hash if self._events else "GENESIS"
        timestamp = utc_now()
        material = f"{timestamp.isoformat()}|{actor_id}|{action}|{target}|{metadata}|{previous_hash}"
        event_hash = sha256(material.encode("utf-8")).hexdigest()
        event = AuditEvent(
            timestamp=timestamp,
            actor_id=actor_id,
            action=action,
            target=target,
            metadata=metadata,
            previous_hash=previous_hash,
            event_hash=event_hash,
        )
        self._events.append(event)
        return event

    def events(self) -> list[AuditEvent]:
        return list(self._events)

    def verify_integrity(self) -> bool:
        previous_hash = "GENESIS"
        for event in self._events:
            material = (
                f"{event.timestamp.isoformat()}|{event.actor_id}|{event.action}|{event.target}|"
                f"{event.metadata}|{previous_hash}"
            )
            expected_hash = sha256(material.encode("utf-8")).hexdigest()
            if expected_hash != event.event_hash:
                return False
            previous_hash = event.event_hash
        return True
