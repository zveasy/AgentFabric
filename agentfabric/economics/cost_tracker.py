"""Cost tracking and spend-limit enforcement."""

from __future__ import annotations

from agentfabric.errors import AuthorizationError
from agentfabric.persistence import PersistenceStore

from .cost_event import CostEvent
from .cost_model import CostModel


class CostTracker:
    def __init__(self, persistence: PersistenceStore, model: CostModel | None = None) -> None:
        self.persistence = persistence
        self.model = model or CostModel()
        self.persistence.initialize()

    def record(self, tenant_id: str, category: str, amount: float | None = None, *, source_id: str = "", metadata: dict[str, object] | None = None) -> CostEvent:
        event = CostEvent(tenant_id=tenant_id, category=category, amount=amount if amount is not None else self.model.estimate(category), source_id=source_id, metadata=metadata or {})
        self.persistence.put("cost_events", event.event_id, event.as_dict())
        return event

    def list_for_tenant(self, tenant_id: str) -> list[CostEvent]:
        return [CostEvent.from_dict(item) for item in self.persistence.list_tenant("cost_events", tenant_id)]

    def total(self, tenant_id: str) -> float:
        return round(sum(event.amount for event in self.list_for_tenant(tenant_id)), 4)

    def set_spend_limits(self, tenant_id: str, limits: dict[str, float]) -> dict[str, object]:
        payload = {"tenant_id": tenant_id, **{key: float(value) for key, value in limits.items()}}
        self.persistence.put("spend_limits", tenant_id, payload)
        return payload

    def spend_limits(self, tenant_id: str) -> dict[str, object]:
        return self.persistence.get("spend_limits", tenant_id) or {"tenant_id": tenant_id}

    def enforce(self, tenant_id: str, category: str, projected_amount: float | None = None, *, source_id: str = "") -> None:
        limits = self.spend_limits(tenant_id)
        projected = projected_amount if projected_amount is not None else self.model.estimate(category)
        tenant_limit = limits.get("tenant_spend_limit")
        if tenant_limit is not None and self.total(tenant_id) + projected > float(tenant_limit):
            raise AuthorizationError("tenant spend limit exceeded")
        specific_keys = {
            "workflow_run": "workflow_spend_limit",
            "agent_run": "agent_spend_limit",
            "tool_execution": "tool_spend_limit",
            "connector_sync": "connector_sync_spend_limit",
            "evaluation_run": "evaluation_run_spend_limit",
        }
        key = specific_keys.get(category)
        if key and limits.get(key) is not None:
            spent = sum(event.amount for event in self.list_for_tenant(tenant_id) if event.category == category and (not source_id or event.source_id == source_id))
            if spent + projected > float(limits[key]):
                raise AuthorizationError(f"{key} exceeded")
