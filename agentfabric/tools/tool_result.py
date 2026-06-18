"""Tool execution result."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class ToolResult:
    tool_id: str
    tenant_id: str
    output: dict[str, object]
    veil_audit_id: str
    classification: str = "internal"
    persisted: bool = False
    execution_id: str = field(default_factory=lambda: f"tool-exec-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "execution_id": self.execution_id,
            "tool_id": self.tool_id,
            "tenant_id": self.tenant_id,
            "output": dict(self.output),
            "classification": self.classification,
            "veil_audit_id": self.veil_audit_id,
            "persisted": self.persisted,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "ToolResult":
        return cls(
            execution_id=str(value["execution_id"]),
            tool_id=str(value["tool_id"]),
            tenant_id=str(value["tenant_id"]),
            output=dict(value.get("output", {})),
            classification=str(value.get("classification", "internal")),
            veil_audit_id=str(value.get("veil_audit_id", "")),
            persisted=bool(value.get("persisted", False)),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
        )
