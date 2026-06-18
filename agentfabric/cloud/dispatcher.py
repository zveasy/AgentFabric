"""Job dispatch and execution enforcement."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Callable

from agentfabric.errors import AuthorizationError, ConflictError
from agentfabric.events import EventStore
from agentfabric.quotas import LimitEnforcer, QuotaPolicy
from veil_client import PolicyCheckRequest, VeilClient

from .job import JobStatus, RuntimeJob
from .job_queue import JobQueue


JobHandler = Callable[[RuntimeJob], dict[str, object]]


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class Dispatcher:
    def __init__(
        self,
        *,
        queue: JobQueue,
        event_store: EventStore,
        veil_client: VeilClient,
        quota_enforcer: LimitEnforcer | None = None,
        quota_policy: Callable[[str], QuotaPolicy] | None = None,
        entitlement_check: Callable[[RuntimeJob], None] | None = None,
        governance_check: Callable[[RuntimeJob], None] | None = None,
        federation_check: Callable[[RuntimeJob], None] | None = None,
        spend_check: Callable[[RuntimeJob], None] | None = None,
    ) -> None:
        self.queue = queue
        self.event_store = event_store
        self.veil_client = veil_client
        self.quota_enforcer = quota_enforcer
        self.quota_policy = quota_policy
        self.entitlement_check = entitlement_check
        self.governance_check = governance_check
        self.federation_check = federation_check
        self.spend_check = spend_check
        self.handlers: dict[str, JobHandler] = {}
        self.latency_ms: list[float] = []

    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        self.handlers[job_type] = handler

    def dispatch_one(self, *, tenant_id: str | None = None, queue_name: str = "default", worker_id: str = "local-worker") -> RuntimeJob | None:
        job = self.queue.dequeue(tenant_id=tenant_id, queue_name=queue_name)
        if job is None:
            return None
        assigned = job.with_update(assigned_worker_id=worker_id)
        self.queue.put(assigned)
        self.event_store.append("runtime.job.assigned", assigned.job_id, assigned.as_dict())
        return self.execute(assigned)

    def execute(self, job: RuntimeJob) -> RuntimeJob:
        job.validate()
        self._enforce(job)
        running = job.with_update(status=JobStatus.RUNNING.value, started_at=utc_now().isoformat())
        self.queue.put(running)
        self.event_store.append("runtime.job.started", running.job_id, running.as_dict())
        started = perf_counter()
        try:
            handler = self.handlers.get(job.job_type, self._default_handler)
            result = handler(running)
            completed = running.with_update(
                status=JobStatus.COMPLETED.value,
                completed_at=utc_now().isoformat(),
                payload={**running.payload, "result": result},
                last_error="",
            )
            self.queue.put(completed)
            self.latency_ms.append((perf_counter() - started) * 1000)
            self.event_store.append("runtime.job.completed", completed.job_id, completed.as_dict())
            return completed
        except Exception as exc:
            failed = running.with_update(status=JobStatus.FAILED.value, last_error=str(exc))
            self.event_store.append("runtime.job.failed", failed.job_id, failed.as_dict())
            if failed.attempts >= failed.max_attempts:
                dead = self.queue.dead_letter(failed)
                self.event_store.append("runtime.job.dead_lettered", dead.job_id, dead.as_dict())
                return dead
            self.queue.put(failed.with_update(status=JobStatus.QUEUED.value))
            self.event_store.append("runtime.job.retried", failed.job_id, failed.as_dict())
            return failed

    def _enforce(self, job: RuntimeJob) -> None:
        if not job.tenant_id:
            raise AuthorizationError("job execution requires tenant context")
        if self.quota_enforcer and self.quota_policy:
            self.quota_enforcer.consume(job.tenant_id, self.quota_policy(job.tenant_id), "compute_seconds")
        if self.spend_check:
            self.spend_check(job)
        if job.job_type == "governance_action" and self.governance_check:
            self.governance_check(job)
        if job.job_type in {"agent_run", "marketplace_package"} and self.entitlement_check:
            self.entitlement_check(job)
        if job.job_type in {
            "remote_discovery_sync",
            "federated_message_send",
            "federated_message_receipt",
            "remote_delegation",
            "revocation_propagation",
            "federation_reputation_recalculation",
        } and self.federation_check:
            self.federation_check(job)
        response = self.veil_client.check_policy(
            PolicyCheckRequest(agent_id=str(job.payload.get("agent_id", job.created_by)), action=f"runtime.execute.{job.job_type}", payload=job.as_dict())
        )
        if not response.allowed:
            raise AuthorizationError(response.reason or "VEIL policy denied job execution")

    def _default_handler(self, job: RuntimeJob) -> dict[str, object]:
        if job.payload.get("force_fail"):
            raise ConflictError("forced job failure")
        return {"job_id": job.job_id, "job_type": job.job_type, "status": "ok"}
