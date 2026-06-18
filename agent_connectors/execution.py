"""Normalized connector execution records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class ConnectorExecution:
    tenant_id: str
    connector_id: str
    connector_version: str
    agent_id: str
    action: str
    status: str
    normalized_result: dict[str, object]
    credential_ref: str
    policy_decision: dict[str, object]
    veil_audit_ref: str | None = None
    error: str | None = None
    execution_id: str = field(default_factory=lambda: f"connector-exec-{uuid4().hex[:12]}")
    timestamp: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "execution_id": self.execution_id,
            "tenant_id": self.tenant_id,
            "connector_id": self.connector_id,
            "connector_version": self.connector_version,
            "agent_id": self.agent_id,
            "action": self.action,
            "status": self.status,
            "normalized_result": dict(self.normalized_result),
            "credential_ref": self.credential_ref,
            "policy_decision": dict(self.policy_decision),
            "veil_audit_ref": self.veil_audit_ref,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }
