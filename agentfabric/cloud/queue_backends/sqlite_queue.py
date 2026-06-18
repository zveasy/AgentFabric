"""SQLite-backed cloud runtime queue."""

from __future__ import annotations

from pathlib import Path

from agentfabric.cloud.job import RuntimeJob
from agentfabric.persistence import SQLitePersistenceStore

from .memory_queue import MemoryJobQueue


class SQLiteJobQueue(MemoryJobQueue):
    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self.store = SQLitePersistenceStore(path)
        self.store.initialize()
        for item in self.store.list("runtime_jobs"):
            job = RuntimeJob.from_dict(item)
            self._jobs[job.job_id] = job
        for item in self.store.list("runtime_dead_letters"):
            job = RuntimeJob.from_dict(item)
            self._dead[job.job_id] = job

    def enqueue(self, job: RuntimeJob) -> RuntimeJob:
        queued = super().enqueue(job)
        self.store.put("runtime_jobs", queued.job_id, queued.as_dict())
        return queued

    def dequeue(self, *, tenant_id: str | None = None, queue_name: str = "default") -> RuntimeJob | None:
        job = super().dequeue(tenant_id=tenant_id, queue_name=queue_name)
        if job:
            self.store.put("runtime_jobs", job.job_id, job.as_dict())
        return job

    def put(self, job: RuntimeJob) -> RuntimeJob:
        saved = super().put(job)
        self.store.put("runtime_jobs", saved.job_id, saved.as_dict())
        return saved

    def dead_letter(self, job: RuntimeJob) -> RuntimeJob:
        dead = super().dead_letter(job)
        self.store.put("runtime_jobs", dead.job_id, dead.as_dict())
        self.store.put("runtime_dead_letters", dead.job_id, dead.as_dict())
        return dead

    def health(self) -> dict[str, object]:
        base = super().health()
        base.update({"backend": "sqlite", "sqlite": self.store.health()})
        return base
