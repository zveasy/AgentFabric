"""Package revenue reporting."""

from __future__ import annotations

from agentfabric.persistence import PersistenceStore

from .revenue_event import RevenueEvent


class PackageRevenue:
    def __init__(self, persistence: PersistenceStore) -> None:
        self.persistence = persistence

    def report(self, package_id: str, tenant_id: str | None = None) -> dict[str, object]:
        events = [
            RevenueEvent.from_dict(item)
            for item in self.persistence.list("revenue_events")
            if item.get("package_id") == package_id and (tenant_id is None or item.get("tenant_id") == tenant_id)
        ]
        return {
            "package_id": package_id,
            "tenant_id": tenant_id,
            "revenue": round(sum(event.amount for event in events), 4),
            "events": [event.as_dict() for event in events],
        }
