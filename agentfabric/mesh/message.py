"""Signed message envelopes for the agent mesh."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class MessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    PUBLISH = "publish"
    SUBSCRIBE = "subscribe"
    DELEGATE = "delegate"


@dataclass(frozen=True)
class MeshMessage:
    source_agent: str
    destination_agent: str | None
    payload: dict[str, object]
    message_type: str = MessageType.REQUEST.value
    timestamp: datetime = field(default_factory=utc_now)
    correlation_id: str = field(default_factory=lambda: f"corr-{uuid4().hex[:12]}")
    task_id: str = field(default_factory=lambda: f"task-{uuid4().hex[:12]}")
    signature: str = ""
    trust_metadata: dict[str, object] = field(default_factory=dict)

    def with_payload_and_trust(
        self,
        payload: dict[str, object],
        trust_metadata: dict[str, object],
        signature: str,
    ) -> "MeshMessage":
        return MeshMessage(
            source_agent=self.source_agent,
            destination_agent=self.destination_agent,
            payload=payload,
            message_type=self.message_type,
            timestamp=self.timestamp,
            correlation_id=self.correlation_id,
            task_id=self.task_id,
            signature=signature,
            trust_metadata=trust_metadata,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "source_agent": self.source_agent,
            "destination_agent": self.destination_agent,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "task_id": self.task_id,
            "message_type": self.message_type,
            "payload": dict(self.payload),
            "signature": self.signature,
            "trust_metadata": dict(self.trust_metadata),
        }
