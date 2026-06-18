"""Durable memory record model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class MemoryRecord:
    owner_agent_id: str
    tenant_id: str
    source_workflow_id: str | None
    classification: str
    content: dict[str, object]
    veil_token_refs: tuple[str, ...] = ()
    memory_type: str = "short_term"
    memory_id: str = field(default_factory=lambda: f"mem-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=utc_now)
    last_accessed_at: datetime = field(default_factory=utc_now)

    def touch(self) -> None:
        self.last_accessed_at = utc_now()

    def as_dict(self) -> dict[str, object]:
        return {
            "memory_id": self.memory_id,
            "owner_agent_id": self.owner_agent_id,
            "tenant_id": self.tenant_id,
            "source_workflow_id": self.source_workflow_id,
            "classification": self.classification,
            "content": dict(self.content),
            "veil_token_refs": list(self.veil_token_refs),
            "memory_type": self.memory_type,
            "created_at": self.created_at.isoformat(),
            "last_accessed_at": self.last_accessed_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "MemoryRecord":
        return cls(
            memory_id=str(value["memory_id"]),
            owner_agent_id=str(value["owner_agent_id"]),
            tenant_id=str(value["tenant_id"]),
            source_workflow_id=str(value["source_workflow_id"]) if value.get("source_workflow_id") else None,
            classification=str(value["classification"]),
            content=dict(value.get("content", {})),
            veil_token_refs=tuple(str(item) for item in value.get("veil_token_refs", ())),
            memory_type=str(value.get("memory_type", "short_term")),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            last_accessed_at=datetime.fromisoformat(str(value["last_accessed_at"])),
        )
