"""In-memory cloud runtime queue."""

from __future__ import annotations

from collections import deque
from copy import deepcopy

from agentfabric.cloud.job import JobStatus, RuntimeJob


class MemoryJobQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, RuntimeJob] = {}
        self._queues: dict[str, deque[str]] = {}
        self._dead: dict[str, RuntimeJob] = {}

    def enqueue(self, job: RuntimeJob) -> RuntimeJob:
        job.validate()
        queued = job.with_update(status=JobStatus.QUEUED.value)
        self._jobs[queued.job_id] = queued
        self._queues.setdefault(queued.queue_name, deque()).append(queued.job_id)
        return deepcopy(queued)

    def dequeue(self, *, tenant_id: str | None = None, queue_name: str = "default") -> RuntimeJob | None:
        queue = self._queues.setdefault(queue_name, deque())
        for _ in range(len(queue)):
            job_id = queue.popleft()
            job = self._jobs.get(job_id)
            if job is None or job.status != JobStatus.QUEUED.value:
                continue
            if tenant_id is not None and job.tenant_id != tenant_id:
                queue.append(job_id)
                continue
            leased = job.with_update(status=JobStatus.ASSIGNED.value, attempts=job.attempts + 1)
            self._jobs[job_id] = leased
            return deepcopy(leased)
        return None

    def put(self, job: RuntimeJob) -> RuntimeJob:
        self._jobs[job.job_id] = job
        if job.status == JobStatus.QUEUED.value:
            queue = self._queues.setdefault(job.queue_name, deque())
            if job.job_id not in queue:
                queue.append(job.job_id)
        return deepcopy(job)

    def get(self, job_id: str) -> RuntimeJob | None:
        job = self._jobs.get(job_id) or self._dead.get(job_id)
        return deepcopy(job) if job else None

    def list(self, *, tenant_id: str | None = None) -> list[RuntimeJob]:
        jobs = sorted(self._jobs.values(), key=lambda item: item.created_at)
        if tenant_id is not None:
            jobs = [job for job in jobs if job.tenant_id == tenant_id]
        return [deepcopy(job) for job in jobs]

    def dead_letter(self, job: RuntimeJob) -> RuntimeJob:
        dead = job.with_update(status=JobStatus.DEAD_LETTERED.value)
        self._jobs[dead.job_id] = dead
        self._dead[dead.job_id] = dead
        return deepcopy(dead)

    def dead_letters(self, *, tenant_id: str | None = None) -> list[RuntimeJob]:
        jobs = sorted(self._dead.values(), key=lambda item: item.updated_at)
        if tenant_id is not None:
            jobs = [job for job in jobs if job.tenant_id == tenant_id]
        return [deepcopy(job) for job in jobs]

    def health(self) -> dict[str, object]:
        return {
            "status": "ok",
            "backend": "memory",
            "queued_jobs": sum(1 for job in self._jobs.values() if job.status == JobStatus.QUEUED.value),
            "dead_letter_jobs": len(self._dead),
        }
