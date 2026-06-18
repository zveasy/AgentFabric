"""Tenant-scoped cloud runtime jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class JobStatus(str, Enum):
    QUEUED = "queued"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD_LETTERED = "dead_lettered"


RUNTIME_JOB_TYPES = {
    "agent_run",
    "workflow_step",
    "mesh_message_delivery",
    "governance_action",
    "marketplace_package",
    "recovery",
    "memory_retention",
    "audit_export",
    "reputation_recalculation",
    "remote_discovery_sync",
    "federated_message_send",
    "federated_message_receipt",
    "remote_delegation",
    "revocation_propagation",
    "federation_reputation_recalculation",
    "connector_sync",
    "connector_search",
    "connector_document_fetch",
    "connector_event_ingestion",
    "connector_webhook_handling",
    "connector_credential_rotation_check",
    "tool_execution",
    "tool_retry",
    "tool_approval_pause",
    "tool_result_persistence",
    "tool_audit_export",
    "tool_reputation_update",
    "evaluation_run",
    "evaluation_gate_check",
    "feedback_ingestion",
    "quality_score_recalculation",
}


@dataclass(frozen=True)
class RuntimeJob:
    tenant_id: str
    organization_id: str
    created_by: str
    job_type: str
    payload: dict[str, object] = field(default_factory=dict)
    queue_name: str = "default"
    max_attempts: int = 3
    job_id: str = field(default_factory=lambda: f"job-{uuid4().hex[:12]}")
    status: str = JobStatus.QUEUED.value
    attempts: int = 0
    assigned_worker_id: str | None = None
    last_error: str = ""
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def validate(self) -> None:
        if not self.tenant_id or not self.organization_id:
            raise ValueError("tenant context is required")
        if self.job_type not in RUNTIME_JOB_TYPES:
            raise ValueError(f"unsupported job type: {self.job_type}")
        if any(str(key).lower() in {"secret", "raw", "password", "token_value"} for key in self.payload):
            raise ValueError("raw sensitive job payload values are not allowed")

    def with_update(self, **updates: object) -> "RuntimeJob":
        data = self.as_dict()
        data.update(updates)
        data["updated_at"] = utc_now().isoformat()
        return RuntimeJob.from_dict(data)

    def as_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "created_by": self.created_by,
            "job_type": self.job_type,
            "payload": dict(self.payload),
            "queue_name": self.queue_name,
            "max_attempts": self.max_attempts,
            "status": self.status,
            "attempts": self.attempts,
            "assigned_worker_id": self.assigned_worker_id,
            "last_error": self.last_error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "RuntimeJob":
        return cls(
            job_id=str(value["job_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            created_by=str(value.get("created_by", "")),
            job_type=str(value["job_type"]),
            payload=dict(value.get("payload", {})),
            queue_name=str(value.get("queue_name", "default")),
            max_attempts=int(value.get("max_attempts", 3)),
            status=str(value.get("status", JobStatus.QUEUED.value)),
            attempts=int(value.get("attempts", 0)),
            assigned_worker_id=str(value["assigned_worker_id"]) if value.get("assigned_worker_id") else None,
            last_error=str(value.get("last_error", "")),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
            updated_at=datetime.fromisoformat(str(value["updated_at"])) if value.get("updated_at") else utc_now(),
            started_at=datetime.fromisoformat(str(value["started_at"])) if value.get("started_at") else None,
            completed_at=datetime.fromisoformat(str(value["completed_at"])) if value.get("completed_at") else None,
        )
