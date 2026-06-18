"""Event-chain integrity validation."""

from __future__ import annotations

from agentfabric.events import EventStore


class IntegrityValidator:
    def __init__(self, event_store: EventStore) -> None:
        self.event_store = event_store

    def validate_or_raise(self) -> None:
        if not self.event_store.validate_integrity():
            raise RuntimeError("event integrity validation failed")
