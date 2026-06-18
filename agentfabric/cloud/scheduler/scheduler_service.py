"""Tenant-aware runtime scheduler."""

from __future__ import annotations

from datetime import datetime, timezone

from agentfabric.cloud.job import RuntimeJob
from agentfabric.cloud.runtime import CloudRuntime
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore

from .cron_parser import CronParser
from .schedule import prepare_schedule
from .scheduled_job import ScheduledJob


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class SchedulerService:
    def __init__(self, *, persistence: PersistenceStore, event_store: EventStore, runtime: CloudRuntime) -> None:
        self.persistence = persistence
        self.event_store = event_store
        self.runtime = runtime

    def create(self, schedule: ScheduledJob) -> ScheduledJob:
        prepared = prepare_schedule(schedule, utc_now())
        self.persistence.put("runtime_schedules", prepared.schedule_id, prepared.as_dict())
        self.event_store.append("runtime.schedule.created", prepared.schedule_id, prepared.as_dict())
        return prepared

    def list(self, tenant_id: str) -> list[ScheduledJob]:
        return [ScheduledJob.from_dict(item) for item in self.persistence.list_tenant("runtime_schedules", tenant_id)]

    def get(self, schedule_id: str) -> ScheduledJob | None:
        item = self.persistence.get("runtime_schedules", schedule_id)
        return ScheduledJob.from_dict(item) if item else None

    def set_enabled(self, schedule_id: str, enabled: bool) -> ScheduledJob:
        schedule = self.get(schedule_id)
        if schedule is None:
            raise KeyError(schedule_id)
        updated = ScheduledJob(
            schedule_id=schedule.schedule_id,
            tenant_id=schedule.tenant_id,
            organization_id=schedule.organization_id,
            created_by=schedule.created_by,
            job_type=schedule.job_type,
            payload=schedule.payload,
            schedule_type=schedule.schedule_type,
            cron=schedule.cron,
            run_at=schedule.run_at,
            enabled=enabled,
            last_run_at=schedule.last_run_at,
            next_run_at=schedule.next_run_at,
            created_at=schedule.created_at,
        )
        self.persistence.put("runtime_schedules", schedule_id, updated.as_dict())
        self.event_store.append("runtime.schedule.enabled" if enabled else "runtime.schedule.disabled", schedule_id, updated.as_dict())
        return updated

    def trigger_due(self, tenant_id: str | None = None, now: datetime | None = None) -> list[RuntimeJob]:
        now = now or utc_now()
        schedules = self.list(tenant_id) if tenant_id else [ScheduledJob.from_dict(item) for item in self.persistence.list("runtime_schedules")]
        triggered: list[RuntimeJob] = []
        for schedule in schedules:
            if not schedule.enabled or schedule.next_run_at is None or schedule.next_run_at > now:
                continue
            job = self.runtime.submit(
                RuntimeJob(
                    tenant_id=schedule.tenant_id,
                    organization_id=schedule.organization_id,
                    created_by=schedule.created_by,
                    job_type=schedule.job_type,
                    payload={**schedule.payload, "schedule_id": schedule.schedule_id},
                )
            )
            triggered.append(job)
            next_run = None
            if schedule.schedule_type == "recurring" and schedule.cron:
                next_run = CronParser().next_after(schedule.cron, now)
            updated = ScheduledJob(
                schedule_id=schedule.schedule_id,
                tenant_id=schedule.tenant_id,
                organization_id=schedule.organization_id,
                created_by=schedule.created_by,
                job_type=schedule.job_type,
                payload=schedule.payload,
                schedule_type=schedule.schedule_type,
                cron=schedule.cron,
                run_at=schedule.run_at,
                enabled=schedule.enabled if next_run is not None else False,
                last_run_at=now,
                next_run_at=next_run,
                created_at=schedule.created_at,
            )
            self.persistence.put("runtime_schedules", schedule.schedule_id, updated.as_dict())
            self.event_store.append("runtime.schedule.triggered", schedule.schedule_id, {"tenant_id": schedule.tenant_id, "job_id": job.job_id})
        return triggered
