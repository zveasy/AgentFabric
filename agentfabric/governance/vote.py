"""Proposal votes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class Vote:
    proposal_id: str
    tenant_id: str
    voter_agent_id: str
    voter_role: str
    vote: str
    weight: int = 1
    reason: str = ""
    vote_id: str = field(default_factory=lambda: f"vote-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "vote_id": self.vote_id,
            "proposal_id": self.proposal_id,
            "tenant_id": self.tenant_id,
            "voter_agent_id": self.voter_agent_id,
            "voter_role": self.voter_role,
            "vote": self.vote,
            "weight": self.weight,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "Vote":
        return cls(
            vote_id=str(value["vote_id"]),
            proposal_id=str(value["proposal_id"]),
            tenant_id=str(value["tenant_id"]),
            voter_agent_id=str(value["voter_agent_id"]),
            voter_role=str(value["voter_role"]),
            vote=str(value["vote"]),
            weight=int(value.get("weight", 1)),
            reason=str(value.get("reason", "")),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
        )
