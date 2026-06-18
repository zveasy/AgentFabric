"""Governed action proposals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .proposal_status import ProposalStatus


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class Proposal:
    tenant_id: str
    organization_id: str
    proposing_agent_id: str
    target_org_id: str
    action_type: str
    risk_level: str
    required_approvals: int
    created_by: str
    target_team_id: str | None = None
    veil_trust_metadata_ref: str | None = None
    consensus_mode: str = "majority"
    status: str = ProposalStatus.PENDING.value
    proposal_id: str = field(default_factory=lambda: f"proposal-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    expires_at: datetime = field(default_factory=lambda: utc_now() + timedelta(hours=24))
    executed_action: dict[str, object] | None = None

    def is_expired(self) -> bool:
        return utc_now() > self.expires_at

    def with_status(self, status: str, *, executed_action: dict[str, object] | None = None) -> "Proposal":
        return Proposal(
            proposal_id=self.proposal_id,
            tenant_id=self.tenant_id,
            organization_id=self.organization_id,
            proposing_agent_id=self.proposing_agent_id,
            target_org_id=self.target_org_id,
            target_team_id=self.target_team_id,
            action_type=self.action_type,
            risk_level=self.risk_level,
            required_approvals=self.required_approvals,
            veil_trust_metadata_ref=self.veil_trust_metadata_ref,
            consensus_mode=self.consensus_mode,
            status=status,
            created_by=self.created_by,
            created_at=self.created_at,
            updated_at=utc_now(),
            expires_at=self.expires_at,
            executed_action=executed_action if executed_action is not None else self.executed_action,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "proposing_agent_id": self.proposing_agent_id,
            "target_org_id": self.target_org_id,
            "target_team_id": self.target_team_id,
            "action_type": self.action_type,
            "risk_level": self.risk_level,
            "required_approvals": self.required_approvals,
            "veil_trust_metadata_ref": self.veil_trust_metadata_ref,
            "consensus_mode": self.consensus_mode,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "executed_action": dict(self.executed_action or {}),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "Proposal":
        return cls(
            proposal_id=str(value["proposal_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            proposing_agent_id=str(value["proposing_agent_id"]),
            target_org_id=str(value["target_org_id"]),
            target_team_id=str(value["target_team_id"]) if value.get("target_team_id") else None,
            action_type=str(value["action_type"]),
            risk_level=str(value.get("risk_level", "medium")),
            required_approvals=int(value.get("required_approvals", 1)),
            veil_trust_metadata_ref=str(value["veil_trust_metadata_ref"]) if value.get("veil_trust_metadata_ref") else None,
            consensus_mode=str(value.get("consensus_mode", "majority")),
            status=str(value.get("status", ProposalStatus.PENDING.value)),
            created_by=str(value.get("created_by", "")),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
            updated_at=datetime.fromisoformat(str(value["updated_at"])) if value.get("updated_at") else utc_now(),
            expires_at=datetime.fromisoformat(str(value["expires_at"])) if value.get("expires_at") else utc_now(),
            executed_action=dict(value.get("executed_action", {})) or None,
        )
