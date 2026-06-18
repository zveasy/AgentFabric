"""Scheduled runtime jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class ScheduledJob:
    tenant_id: str
    organization_id: str
    created_by: str
    job_type: str
    payload: dict[str, object]
    schedule_type: str = "one_time"
    cron: str | None = None
    run_at: datetime | None = None
    enabled: bool = True
    schedule_id: str = field(default_factory=lambda: f"schedule-{uuid4().hex[:12]}")
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "schedule_id": self.schedule_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "created_by": self.created_by,
            "job_type": self.job_type,
            "payload": dict(self.payload),
            "schedule_type": self.schedule_type,
            "cron": self.cron,
            "run_at": self.run_at.isoformat() if self.run_at else None,
            "enabled": self.enabled,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "ScheduledJob":
        return cls(
            schedule_id=str(value["schedule_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            created_by=str(value.get("created_by", "")),
            job_type=str(value["job_type"]),
            payload=dict(value.get("payload", {})),
            schedule_type=str(value.get("schedule_type", "one_time")),
            cron=str(value["cron"]) if value.get("cron") else None,
            run_at=datetime.fromisoformat(str(value["run_at"])) if value.get("run_at") else None,
            enabled=bool(value.get("enabled", True)),
            last_run_at=datetime.fromisoformat(str(value["last_run_at"])) if value.get("last_run_at") else None,
            next_run_at=datetime.fromisoformat(str(value["next_run_at"])) if value.get("next_run_at") else None,
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
        )
