"""Versioned protocol envelopes for agent runtime messages."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


ProtocolMessageType = Literal[
    "request",
    "response",
    "event",
    "capability_discovery",
    "tool_invocation",
    "tool_result",
]


@dataclass(frozen=True)
class ProtocolEnvelope:
    protocol_version: str
    message_type: ProtocolMessageType
    correlation_id: str
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=utc_now)

    @classmethod
    def build(cls, message_type: ProtocolMessageType, payload: dict[str, Any], protocol_version: str = "v1") -> "ProtocolEnvelope":
        return cls(
            protocol_version=protocol_version,
            message_type=message_type,
            correlation_id=str(uuid4()),
            payload=payload,
        )

    def to_json(self) -> str:
        body = asdict(self)
        body["timestamp"] = self.timestamp.isoformat()
        return json.dumps(body, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "ProtocolEnvelope":
        body = json.loads(raw)
        body["timestamp"] = datetime.fromisoformat(body["timestamp"])
        return cls(**body)
