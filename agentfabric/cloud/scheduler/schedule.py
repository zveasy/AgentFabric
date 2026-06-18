"""Schedule construction helpers."""

from __future__ import annotations

from datetime import datetime

from .cron_parser import CronParser
from .scheduled_job import ScheduledJob


def prepare_schedule(schedule: ScheduledJob, now: datetime) -> ScheduledJob:
    next_run = schedule.run_at
    if schedule.schedule_type == "recurring":
        if not schedule.cron:
            raise ValueError("recurring schedule requires cron")
        next_run = CronParser().next_after(schedule.cron, now)
    return ScheduledJob(
        schedule_id=schedule.schedule_id,
        tenant_id=schedule.tenant_id,
        organization_id=schedule.organization_id,
        created_by=schedule.created_by,
        job_type=schedule.job_type,
        payload=schedule.payload,
        schedule_type=schedule.schedule_type,
        cron=schedule.cron,
        run_at=schedule.run_at,
        enabled=schedule.enabled,
        last_run_at=schedule.last_run_at,
        next_run_at=next_run,
        created_at=schedule.created_at,
    )
