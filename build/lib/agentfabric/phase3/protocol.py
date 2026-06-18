"""Agent-to-agent message protocol extensions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class TraceContext:
    correlation_id: str
    parent_span_id: str | None = None


@dataclass(frozen=True)
class CollaborationMessage:
    message_type: Literal["handoff", "delegate", "result", "error"]
    source_agent: str
    target_agent: str
    payload: dict[str, Any]
    trace: TraceContext
    timeout_seconds: float = 30.0
    created_at: datetime = field(default_factory=utc_now)
