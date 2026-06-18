"""Connector execution result."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class ConnectorResult:
    connector_id: str
    tenant_id: str
    operation: str
    sanitized_payload: dict[str, object]
    veil_audit_id: str
    token_refs: tuple[str, ...] = ()
    result_id: str = ""
    created_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "result_id": self.result_id or f"{self.connector_id}:{self.operation}:{int(self.created_at.timestamp())}",
            "connector_id": self.connector_id,
            "tenant_id": self.tenant_id,
            "operation": self.operation,
            "sanitized_payload": dict(self.sanitized_payload),
            "veil_audit_id": self.veil_audit_id,
            "token_refs": list(self.token_refs),
            "created_at": self.created_at.isoformat(),
        }
