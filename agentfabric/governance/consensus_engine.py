"""Consensus evaluation for governed proposals."""

from __future__ import annotations

from dataclasses import dataclass

from agentfabric.errors import AuthorizationError, ValidationError

from .agent_role import AUTHORIZED_VOTING_ROLES
from .consensus_policy import ConsensusPolicy
from .governance_policy import GovernancePolicy
from .proposal import Proposal
from .vote import Vote


@dataclass(frozen=True)
class ConsensusResult:
    reached: bool
    status: str
    reason: str
    approvals: int
    rejections: int
    abstentions: int

    def as_dict(self) -> dict[str, object]:
        return {
            "reached": self.reached,
            "status": self.status,
            "reason": self.reason,
            "approvals": self.approvals,
            "rejections": self.rejections,
            "abstentions": self.abstentions,
        }


class ConsensusEngine:
    def evaluate(
        self,
        proposal: Proposal,
        votes: list[Vote],
        policy: ConsensusPolicy,
        governance_policy: GovernancePolicy,
    ) -> ConsensusResult:
        if proposal.is_expired():
            return ConsensusResult(False, "expired", "proposal expired", 0, 0, 0)
        if not governance_policy.risk_within_agent_authority(proposal.risk_level) and policy.mode != "human_required":
            return ConsensusResult(False, "blocked", "proposal risk exceeds agent authority", 0, 0, 0)
        if not votes:
            return ConsensusResult(False, "pending", "required voters are missing", 0, 0, 0)

        for vote in votes:
            if vote.voter_role not in AUTHORIZED_VOTING_ROLES:
                raise AuthorizationError("agent cannot vote outside authorized role")
            if vote.vote not in {"approve", "reject", "abstain", "escalate"}:
                raise ValidationError(f"unsupported vote: {vote.vote}")

        approvals = [vote for vote in votes if vote.vote == "approve"]
        rejections = [vote for vote in votes if vote.vote == "reject"]
        abstentions = [vote for vote in votes if vote.vote == "abstain"]
        escalations = [vote for vote in votes if vote.vote == "escalate"]
        counted = approvals + rejections

        if escalations:
            return ConsensusResult(False, "escalated", "proposal escalated", len(approvals), len(rejections), len(abstentions))
        if rejections and policy.mode in {"single_approver", "unanimous"}:
            return ConsensusResult(False, "rejected", "proposal rejected", len(approvals), len(rejections), len(abstentions))
        missing_roles = [role for role in policy.required_roles if role not in {vote.voter_role for vote in approvals}]
        if missing_roles:
            return ConsensusResult(False, "pending", f"missing required approver roles: {', '.join(missing_roles)}", len(approvals), len(rejections), len(abstentions))

        required_approvals = max(policy.required_approvals, proposal.required_approvals)
        if len(approvals) < required_approvals:
            return ConsensusResult(False, "pending", "not enough approvals", len(approvals), len(rejections), len(abstentions))

        mode = policy.mode
        if mode == "single_approver":
            return ConsensusResult(True, "approved", "single approver consensus reached", len(approvals), len(rejections), len(abstentions))
        if mode == "majority":
            total = max(len(counted), required_approvals)
            return ConsensusResult(len(approvals) > total / 2, "approved" if len(approvals) > total / 2 else "pending", "majority evaluated", len(approvals), len(rejections), len(abstentions))
        if mode == "supermajority":
            total = max(len(counted), required_approvals)
            reached = (len(approvals) / total) >= max(policy.threshold, 2 / 3)
            return ConsensusResult(reached, "approved" if reached else "pending", "supermajority evaluated", len(approvals), len(rejections), len(abstentions))
        if mode == "unanimous":
            reached = not rejections and len(approvals) >= required_approvals and len(counted) == len(approvals)
            return ConsensusResult(reached, "approved" if reached else "pending", "unanimous evaluated", len(approvals), len(rejections), len(abstentions))
        if mode == "weighted":
            total_weight = sum(vote.weight for vote in counted)
            approval_weight = sum(vote.weight for vote in approvals)
            reached = total_weight > 0 and (approval_weight / total_weight) >= policy.threshold
            return ConsensusResult(reached, "approved" if reached else "pending", "weighted consensus evaluated", len(approvals), len(rejections), len(abstentions))
        if mode == "human_required":
            return ConsensusResult(True, "awaiting_human", "human approval required", len(approvals), len(rejections), len(abstentions))
        if mode == "security_required":
            required = ConsensusPolicy(mode="majority", required_roles=("security_reviewer",), required_approvals=required_approvals)
            return self.evaluate(proposal, votes, required, governance_policy)
        if mode == "compliance_required":
            required = ConsensusPolicy(mode="majority", required_roles=("compliance_reviewer",), required_approvals=required_approvals)
            return self.evaluate(proposal, votes, required, governance_policy)
        raise ValidationError(f"unsupported consensus mode: {mode}")
