"""Cloud runtime facade."""

from __future__ import annotations

from collections.abc import Callable

from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore
from agentfabric.quotas import LimitEnforcer, QuotaPolicy
from veil_client import VeilClient

from .dispatcher import Dispatcher
from .job import JobStatus, RuntimeJob
from .job_queue import JobQueue
from .runtime_config import RuntimeConfig
from .worker import Worker
from .worker_pool import WorkerPool


class CloudRuntime:
    def __init__(
        self,
        *,
        queue: JobQueue,
        persistence: PersistenceStore,
        event_store: EventStore,
        veil_client: VeilClient,
        config: RuntimeConfig | None = None,
        quota_enforcer: LimitEnforcer | None = None,
        quota_policy: Callable[[str], QuotaPolicy] | None = None,
    ) -> None:
        self.queue = queue
        self.persistence = persistence
        self.event_store = event_store
        self.config = config or RuntimeConfig()
        self.workers = WorkerPool(
            persistence=persistence,
            event_store=event_store,
            heartbeat_timeout_seconds=self.config.heartbeat_timeout_seconds,
        )
        self.dispatcher = Dispatcher(
            queue=queue,
            event_store=event_store,
            veil_client=veil_client,
            quota_enforcer=quota_enforcer,
            quota_policy=quota_policy,
        )

    def submit(self, job: RuntimeJob) -> RuntimeJob:
        job.validate()
        queued = self.queue.enqueue(job)
        self.event_store.append("runtime.job.created", queued.job_id, queued.as_dict())
        return queued

    def list_jobs(self, tenant_id: str | None = None) -> list[RuntimeJob]:
        return self.queue.list(tenant_id=tenant_id)

    def get_job(self, job_id: str) -> RuntimeJob | None:
        return self.queue.get(job_id)

    def cancel(self, job_id: str) -> RuntimeJob:
        job = self.queue.get(job_id)
        if job is None:
            raise KeyError(job_id)
        cancelled = job.with_update(status=JobStatus.CANCELLED.value)
        self.queue.put(cancelled)
        self.event_store.append("runtime.job.cancelled", cancelled.job_id, cancelled.as_dict())
        return cancelled

    def retry(self, job_id: str) -> RuntimeJob:
        job = self.queue.get(job_id)
        if job is None:
            raise KeyError(job_id)
        retried = job.with_update(status=JobStatus.QUEUED.value, last_error="")
        self.queue.put(retried)
        self.event_store.append("runtime.job.retried", retried.job_id, retried.as_dict())
        return retried

    def requeue_dead_letter(self, job_id: str) -> RuntimeJob:
        job = self.queue.get(job_id)
        if job is None:
            raise KeyError(job_id)
        requeued = job.with_update(status=JobStatus.QUEUED.value, last_error="")
        self.queue.enqueue(requeued)
        self.event_store.append("runtime.job.retried", requeued.job_id, requeued.as_dict())
        return requeued

    def register_worker(self, worker: Worker) -> Worker:
        return self.workers.register(worker)

    def heartbeat(self, worker_id: str) -> Worker:
        return self.workers.heartbeat(worker_id, lease_seconds=self.config.worker_lease_seconds)

    def health(self) -> dict[str, object]:
        self.workers.mark_stale_workers()
        queue_health = self.queue.health()
        worker_items = self.workers.list()
        status = "ok" if queue_health.get("status") == "ok" else "degraded"
        return {
            "status": status,
            "queue": queue_health,
            "workers": {"count": len(worker_items), "healthy": sum(1 for worker in worker_items if worker.status == "healthy")},
            "event_integrity": self.event_store.validate_integrity(),
        }
