"""Revenue tracking."""

from __future__ import annotations

from agentfabric.persistence import PersistenceStore

from .revenue_event import RevenueEvent
from .revenue_model import RevenueModel


class RevenueTracker:
    def __init__(self, persistence: PersistenceStore, model: RevenueModel | None = None) -> None:
        self.persistence = persistence
        self.model = model or RevenueModel()
        self.persistence.initialize()

    def record(self, tenant_id: str, category: str, amount: float | None = None, *, source_id: str = "", package_id: str | None = None, metadata: dict[str, object] | None = None) -> RevenueEvent:
        event = RevenueEvent(tenant_id=tenant_id, category=category, amount=amount if amount is not None else self.model.estimate(category), source_id=source_id, package_id=package_id, metadata=metadata or {})
        self.persistence.put("revenue_events", event.event_id, event.as_dict())
        return event

    def list_for_tenant(self, tenant_id: str) -> list[RevenueEvent]:
        return [RevenueEvent.from_dict(item) for item in self.persistence.list_tenant("revenue_events", tenant_id)]

    def total(self, tenant_id: str) -> float:
        return round(sum(event.amount for event in self.list_for_tenant(tenant_id)), 4)
