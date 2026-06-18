"""In-memory reputation service."""

from __future__ import annotations

from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore

from .models import ReputationRecord


class ReputationService:
    def __init__(self, persistence: PersistenceStore | None = None) -> None:
        self.persistence = persistence
        self._records: dict[str, ReputationRecord] = {}
        self._timeline: dict[str, list[dict[str, object]]] = {}
        if self.persistence is not None:
            self.persistence.initialize()
            for item in self.persistence.list("reputation"):
                record = _record_from_dict(item)
                key = _key(record.agent_id, str(item["tenant_id"]) if item.get("tenant_id") else None)
                self._records[key] = record
                self._timeline[key] = list(item.get("timeline", []))

    def get(self, agent_id: str, tenant_id: str | None = None) -> ReputationRecord:
        key = _key(agent_id, tenant_id)
        if key not in self._records:
            self._records[key] = ReputationRecord(agent_id=agent_id)
            self._persist(agent_id, tenant_id=tenant_id)
        return self._records[key]

    def record_task(
        self,
        agent_id: str,
        *,
        success: bool,
        latency_ms: float,
        tenant_id: str | None = None,
    ) -> ReputationRecord:
        record = self.get(agent_id, tenant_id=tenant_id)
        if success:
            record.successful_tasks += 1
        else:
            record.failures += 1
        record.total_latency_ms += latency_ms
        key = _key(agent_id, tenant_id)
        self._timeline.setdefault(key, []).append(
            {"event": "task", "success": success, "latency_ms": latency_ms}
        )
        self._persist(agent_id, tenant_id=tenant_id)
        return record

    def record_rating(self, agent_id: str, rating: float, tenant_id: str | None = None) -> ReputationRecord:
        record = self.get(agent_id, tenant_id=tenant_id)
        record.human_ratings_total += rating
        record.human_ratings_count += 1
        key = _key(agent_id, tenant_id)
        self._timeline.setdefault(key, []).append({"event": "rating", "rating": rating})
        self._persist(agent_id, tenant_id=tenant_id)
        return record

    def record_approval(self, agent_id: str, approved: bool, tenant_id: str | None = None) -> ReputationRecord:
        record = self.get(agent_id, tenant_id=tenant_id)
        record.approval_requests += 1
        if approved:
            record.approvals += 1
        key = _key(agent_id, tenant_id)
        self._timeline.setdefault(key, []).append({"event": "approval", "approved": approved})
        self._persist(agent_id, tenant_id=tenant_id)
        return record

    def timeline(self, agent_id: str, tenant_id: str | None = None) -> list[dict[str, object]]:
        self.get(agent_id, tenant_id=tenant_id)
        return list(self._timeline.get(_key(agent_id, tenant_id), []))

    def reconstruct_from_events(self, event_store: EventStore) -> None:
        self._records.clear()
        self._timeline.clear()
        for event in event_store.replay():
            if event.event_type in {"task.completed", "task.failed"}:
                agent_id = str(event.payload.get("agent_id", ""))
                if not agent_id:
                    continue
                self.record_task(
                    agent_id,
                    success=event.event_type == "task.completed",
                    latency_ms=float(event.payload.get("latency_ms", 0.0)),
                    tenant_id=str(event.payload["tenant_id"]) if event.payload.get("tenant_id") else None,
                )
            elif event.event_type == "reputation.updated":
                agent_id = str(event.payload.get("agent_id", ""))
                if agent_id and "rating" in event.payload:
                    self.record_rating(
                        agent_id,
                        float(event.payload["rating"]),
                        tenant_id=str(event.payload["tenant_id"]) if event.payload.get("tenant_id") else None,
                    )

    def _persist(self, agent_id: str, tenant_id: str | None = None) -> None:
        if self.persistence is None:
            return
        key = _key(agent_id, tenant_id)
        record = self._records[key]
        payload = record.as_dict()
        payload.update(
            {
                "tenant_id": tenant_id,
                "total_latency_ms": record.total_latency_ms,
                "human_ratings_total": record.human_ratings_total,
                "human_ratings_count": record.human_ratings_count,
                "approvals": record.approvals,
                "approval_requests": record.approval_requests,
                "timeline": list(self._timeline.get(key, [])),
            }
        )
        self.persistence.put("reputation", key, payload)


def _record_from_dict(value: dict[str, object]) -> ReputationRecord:
    return ReputationRecord(
        agent_id=str(value["agent_id"]),
        successful_tasks=int(value.get("successful_tasks", 0)),
        failures=int(value.get("failures", 0)),
        total_latency_ms=float(value.get("total_latency_ms", 0.0)),
        human_ratings_total=float(value.get("human_ratings_total", 0.0)),
        human_ratings_count=int(value.get("human_ratings_count", 0)),
        approvals=int(value.get("approvals", 0)),
        approval_requests=int(value.get("approval_requests", 0)),
    )


def _key(agent_id: str, tenant_id: str | None = None) -> str:
    return f"{tenant_id}:{agent_id}" if tenant_id else agent_id
