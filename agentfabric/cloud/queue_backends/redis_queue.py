"""Redis cloud runtime queue with local fallback."""

from __future__ import annotations

import json

from agentfabric.cloud.job import JobStatus, RuntimeJob

from .memory_queue import MemoryJobQueue


class RedisJobQueue(MemoryJobQueue):
    def __init__(self, redis_url: str, *, fallback: bool = True) -> None:
        super().__init__()
        self.redis_url = redis_url
        self._client = None
        self._fallback = False
        try:
            from redis import Redis
            self._client = Redis.from_url(redis_url, decode_responses=True)
            self._client.ping()
        except Exception:
            if not fallback:
                raise
            self._client = None
            self._fallback = True

    def enqueue(self, job: RuntimeJob) -> RuntimeJob:
        queued = super().enqueue(job)
        if self._client is not None:
            self._client.lpush(f"af:runtime:{queued.queue_name}", queued.job_id)
            self._client.hset("af:runtime:jobs", queued.job_id, json.dumps(queued.as_dict(), sort_keys=True))
        return queued

    def dequeue(self, *, tenant_id: str | None = None, queue_name: str = "default") -> RuntimeJob | None:
        if self._client is None:
            return super().dequeue(tenant_id=tenant_id, queue_name=queue_name)
        for _ in range(int(self._client.llen(f"af:runtime:{queue_name}"))):
            job_id = self._client.rpop(f"af:runtime:{queue_name}")
            if job_id is None:
                return None
            raw = self._client.hget("af:runtime:jobs", job_id)
            if raw is None:
                continue
            job = RuntimeJob.from_dict(json.loads(raw))
            if tenant_id is not None and job.tenant_id != tenant_id:
                self._client.lpush(f"af:runtime:{queue_name}", job_id)
                continue
            leased = job.with_update(status=JobStatus.ASSIGNED.value, attempts=job.attempts + 1)
            self.put(leased)
            return leased
        return None

    def put(self, job: RuntimeJob) -> RuntimeJob:
        saved = super().put(job)
        if self._client is not None:
            self._client.hset("af:runtime:jobs", saved.job_id, json.dumps(saved.as_dict(), sort_keys=True))
        return saved

    def dead_letter(self, job: RuntimeJob) -> RuntimeJob:
        dead = super().dead_letter(job)
        if self._client is not None:
            self._client.hset("af:runtime:dead", dead.job_id, json.dumps(dead.as_dict(), sort_keys=True))
        return dead

    def health(self) -> dict[str, object]:
        base = super().health()
        base.update({"backend": "redis-fallback" if self._fallback else "redis"})
        if self._client is not None:
            base["redis_ping"] = bool(self._client.ping())
        return base
