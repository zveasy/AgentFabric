"""Conversation context exchanged through the mesh."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class ConversationContext:
    conversation_id: str
    task_id: str
    participants: set[str] = field(default_factory=set)
    state: dict[str, object] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=utc_now)

    def add_participant(self, agent_id: str) -> None:
        self.participants.add(agent_id)
        self.updated_at = utc_now()

    def update_state(self, values: dict[str, object]) -> None:
        self.state.update(values)
        self.updated_at = utc_now()

    def as_dict(self) -> dict[str, object]:
        return {
            "conversation_id": self.conversation_id,
            "task_id": self.task_id,
            "participants": sorted(self.participants),
            "state": dict(self.state),
            "updated_at": self.updated_at.isoformat(),
        }
