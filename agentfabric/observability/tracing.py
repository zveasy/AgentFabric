"""Minimal runtime tracing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class TraceSpan:
    name: str
    tenant_id: str
    span_id: str = field(default_factory=lambda: f"span-{uuid4().hex[:12]}")
    started_at: datetime = field(default_factory=utc_now)
    ended_at: datetime | None = None

    def finish(self) -> "TraceSpan":
        return TraceSpan(name=self.name, tenant_id=self.tenant_id, span_id=self.span_id, started_at=self.started_at, ended_at=utc_now())

    def as_dict(self) -> dict[str, object]:
        return {
            "span_id": self.span_id,
            "name": self.name,
            "tenant_id": self.tenant_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }
