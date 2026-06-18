"""Worker registry and heartbeat tracking."""

from __future__ import annotations

from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore

from .worker import Worker


class WorkerPool:
    def __init__(self, *, persistence: PersistenceStore, event_store: EventStore, heartbeat_timeout_seconds: int = 90) -> None:
        self.persistence = persistence
        self.event_store = event_store
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds

    def register(self, worker: Worker) -> Worker:
        self.persistence.put("runtime_workers", worker.worker_id, worker.as_dict())
        self.event_store.append("runtime.worker.registered", worker.worker_id, worker.as_dict())
        return worker

    def heartbeat(self, worker_id: str, *, lease_seconds: int = 60) -> Worker:
        worker = self.get(worker_id)
        if worker is None:
            raise KeyError(worker_id)
        updated = worker.heartbeat(lease_seconds)
        self.persistence.put("runtime_workers", worker_id, updated.as_dict())
        return updated

    def get(self, worker_id: str) -> Worker | None:
        item = self.persistence.get("runtime_workers", worker_id)
        return Worker.from_dict(item) if item else None

    def list(self, tenant_id: str | None = None) -> list[Worker]:
        items = self.persistence.list_tenant("runtime_workers", tenant_id) if tenant_id else self.persistence.list("runtime_workers")
        return [Worker.from_dict(item) for item in items]

    def mark_stale_workers(self) -> list[Worker]:
        stale: list[Worker] = []
        for worker in self.list():
            if worker.is_stale(self.heartbeat_timeout_seconds) and worker.status != "stale":
                updated = Worker(
                    worker_id=worker.worker_id,
                    tenant_id=worker.tenant_id,
                    queue_names=worker.queue_names,
                    capabilities=worker.capabilities,
                    status="stale",
                    lease_until=worker.lease_until,
                    registered_at=worker.registered_at,
                    last_heartbeat_at=worker.last_heartbeat_at,
                )
                self.persistence.put("runtime_workers", worker.worker_id, updated.as_dict())
                self.event_store.append("runtime.worker.heartbeat_missed", worker.worker_id, updated.as_dict())
                stale.append(updated)
        return stale
