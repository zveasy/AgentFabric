"""Per-tenant runtime usage metrics."""

from __future__ import annotations

from agentfabric.cloud.job import JobStatus
from agentfabric.cloud.runtime import CloudRuntime


class TenantUsageMetrics:
    def __init__(self, runtime: CloudRuntime) -> None:
        self.runtime = runtime

    def snapshot(self, tenant_id: str) -> dict[str, object]:
        jobs = self.runtime.list_jobs(tenant_id)
        return {
            "tenant_id": tenant_id,
            "jobs_total": len(jobs),
            "jobs_queued": sum(1 for job in jobs if job.status == JobStatus.QUEUED.value),
            "jobs_completed": sum(1 for job in jobs if job.status == JobStatus.COMPLETED.value),
            "jobs_failed": sum(1 for job in jobs if job.status == JobStatus.FAILED.value),
            "jobs_dead_lettered": sum(1 for job in jobs if job.status == JobStatus.DEAD_LETTERED.value),
        }
