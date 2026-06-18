"""Connector runtime audit helpers."""

from __future__ import annotations

from agentfabric.events import EventStore


class ConnectorAudit:
    def __init__(self, event_store: EventStore) -> None:
        self.event_store = event_store

    def emit(self, event_type: str, aggregate_id: str, payload: dict[str, object]) -> dict[str, object]:
        return self.event_store.append(event_type, aggregate_id, payload).as_dict()
