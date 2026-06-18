"""Queue abstraction for tenant-scoped runtime jobs."""

from __future__ import annotations

from typing import Protocol

from .job import RuntimeJob


class JobQueue(Protocol):
    def enqueue(self, job: RuntimeJob) -> RuntimeJob:
        """Add a job to the queue."""

    def dequeue(self, *, tenant_id: str | None = None, queue_name: str = "default") -> RuntimeJob | None:
        """Lease the next queued job."""

    def put(self, job: RuntimeJob) -> RuntimeJob:
        """Persist a job update."""

    def get(self, job_id: str) -> RuntimeJob | None:
        """Fetch a job by id."""

    def list(self, *, tenant_id: str | None = None) -> list[RuntimeJob]:
        """List jobs, tenant-filtered unless elevated by caller."""

    def dead_letter(self, job: RuntimeJob) -> RuntimeJob:
        """Move a job to the dead-letter queue."""

    def dead_letters(self, *, tenant_id: str | None = None) -> list[RuntimeJob]:
        """List dead-letter jobs."""

    def health(self) -> dict[str, object]:
        """Backend health."""
