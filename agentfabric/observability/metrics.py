"""Runtime metrics snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field

from agentfabric.cloud.job import JobStatus
from agentfabric.cloud.runtime import CloudRuntime


@dataclass
class MetricsRegistry:
    workflow_latency_ms: list[float] = field(default_factory=list)
    agent_run_latency_ms: list[float] = field(default_factory=list)
    veil_policy_latency_ms: list[float] = field(default_factory=list)
    marketplace_install_latency_ms: list[float] = field(default_factory=list)
    governance_approval_latency_ms: list[float] = field(default_factory=list)

    def runtime_snapshot(self, runtime: CloudRuntime) -> dict[str, object]:
        jobs = runtime.list_jobs()
        return {
            "worker_count": len(runtime.workers.list()),
            "active_jobs": sum(1 for job in jobs if job.status in {JobStatus.ASSIGNED.value, JobStatus.RUNNING.value}),
            "queued_jobs": sum(1 for job in jobs if job.status == JobStatus.QUEUED.value),
            "failed_jobs": sum(1 for job in jobs if job.status == JobStatus.FAILED.value),
            "dead_letter_jobs": len(runtime.queue.dead_letters()),
            "workflow_latency_ms": self._summary(self.workflow_latency_ms),
            "agent_run_latency_ms": self._summary(self.agent_run_latency_ms),
            "veil_policy_latency_ms": self._summary(self.veil_policy_latency_ms),
            "marketplace_install_latency_ms": self._summary(self.marketplace_install_latency_ms),
            "governance_approval_latency_ms": self._summary(self.governance_approval_latency_ms),
        }

    def _summary(self, values: list[float]) -> dict[str, float]:
        if not values:
            return {"count": 0, "avg": 0.0}
        return {"count": len(values), "avg": round(sum(values) / len(values), 3)}
