"""Auditable governance decision records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from .proposal import Proposal
from .vote import Vote


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class DecisionRecord:
    proposal_id: str
    tenant_id: str
    proposal_summary: dict[str, object]
    voters: tuple[str, ...]
    votes: tuple[dict[str, object], ...]
    consensus_result: dict[str, object]
    human_approvals: tuple[dict[str, object], ...]
    executed_action: dict[str, object]
    risk_summary: dict[str, object]
    veil_audit_refs: tuple[str, ...]
    event_ids: tuple[str, ...]
    final_status: str
    decision_record_id: str = field(default_factory=lambda: f"decision-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "decision_record_id": self.decision_record_id,
            "proposal_id": self.proposal_id,
            "tenant_id": self.tenant_id,
            "proposal_summary": dict(self.proposal_summary),
            "voters": list(self.voters),
            "votes": [dict(vote) for vote in self.votes],
            "consensus_result": dict(self.consensus_result),
            "human_approvals": [dict(item) for item in self.human_approvals],
            "executed_action": dict(self.executed_action),
            "risk_summary": dict(self.risk_summary),
            "veil_audit_refs": list(self.veil_audit_refs),
            "event_ids": list(self.event_ids),
            "final_status": self.final_status,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "DecisionRecord":
        return cls(
            decision_record_id=str(value["decision_record_id"]),
            proposal_id=str(value["proposal_id"]),
            tenant_id=str(value["tenant_id"]),
            proposal_summary=dict(value.get("proposal_summary", {})),
            voters=tuple(str(item) for item in value.get("voters", ())),
            votes=tuple(dict(item) for item in value.get("votes", ())),
            consensus_result=dict(value.get("consensus_result", {})),
            human_approvals=tuple(dict(item) for item in value.get("human_approvals", ())),
            executed_action=dict(value.get("executed_action", {})),
            risk_summary=dict(value.get("risk_summary", {})),
            veil_audit_refs=tuple(str(item) for item in value.get("veil_audit_refs", ())),
            event_ids=tuple(str(item) for item in value.get("event_ids", ())),
            final_status=str(value.get("final_status", "")),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
        )

    @classmethod
    def build(
        cls,
        *,
        proposal: Proposal,
        votes: list[Vote],
        consensus_result: dict[str, object],
        human_approvals: list[dict[str, object]],
        executed_action: dict[str, object],
        veil_audit_refs: tuple[str, ...],
        event_ids: tuple[str, ...],
    ) -> "DecisionRecord":
        return cls(
            proposal_id=proposal.proposal_id,
            tenant_id=proposal.tenant_id,
            proposal_summary={
                "action_type": proposal.action_type,
                "risk_level": proposal.risk_level,
                "target_org_id": proposal.target_org_id,
                "target_team_id": proposal.target_team_id,
                "veil_trust_metadata_ref": proposal.veil_trust_metadata_ref,
            },
            voters=tuple(vote.voter_agent_id for vote in votes),
            votes=tuple(
                {
                    "voter_agent_id": vote.voter_agent_id,
                    "voter_role": vote.voter_role,
                    "vote": vote.vote,
                    "weight": vote.weight,
                }
                for vote in votes
            ),
            consensus_result=consensus_result,
            human_approvals=tuple(human_approvals),
            executed_action=executed_action,
            risk_summary={"risk_level": proposal.risk_level, "raw_sensitive_values_persisted": False},
            veil_audit_refs=veil_audit_refs,
            event_ids=event_ids,
            final_status=proposal.status,
        )
