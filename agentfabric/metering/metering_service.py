"""Usage metering service."""

from __future__ import annotations

from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore

from .aggregation import aggregate_usage
from .usage_event import UsageEvent


class MeteringService:
    def __init__(self, persistence: PersistenceStore) -> None:
        self.persistence = persistence
        self.persistence.initialize()

    def record(self, tenant_id: str, event_type: str, quantity: int = 1, metadata: dict[str, object] | None = None) -> UsageEvent:
        event = UsageEvent(
            tenant_id=tenant_id,
            event_type=event_type,
            quantity=quantity,
            metadata=metadata or {},
        )
        self.persistence.put("usage_events", event.usage_id, event.as_dict())
        return event

    def list_for_tenant(self, tenant_id: str) -> list[UsageEvent]:
        return [UsageEvent.from_dict(item) for item in self.persistence.list_tenant("usage_events", tenant_id)]

    def aggregate(self, tenant_id: str) -> dict[str, int]:
        return aggregate_usage(self.list_for_tenant(tenant_id))

    def reconstruct_from_events(self, tenant_id: str, event_store: EventStore) -> dict[str, int]:
        mapped: dict[str, int] = {}
        for event in event_store.replay():
            if event.payload.get("tenant_id") != tenant_id:
                continue
            usage_type = {
                "workflow.started": "workflow_runs",
                "task.completed": "task_executions",
                "task.failed": "task_executions",
                "message": "message_sends",
                "memory.recorded": "memory_writes",
                "memory.deleted": "memory_deletes",
            }.get(event.event_type)
            if usage_type:
                mapped[usage_type] = mapped.get(usage_type, 0) + 1
        return mapped
