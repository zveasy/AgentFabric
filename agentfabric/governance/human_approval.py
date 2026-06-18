"""Human approval bridge for governed proposals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from agentfabric.errors import ConflictError
from agentfabric.persistence import PersistenceStore


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class HumanApproval:
    proposal_id: str
    tenant_id: str
    assigned_reviewer: str
    status: str = "pending"
    reason: str = ""
    approval_id: str = field(default_factory=lambda: f"approval-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=utc_now)
    expires_at: datetime = field(default_factory=lambda: utc_now() + timedelta(hours=24))
    resolved_at: datetime | None = None

    def is_expired(self) -> bool:
        return utc_now() > self.expires_at

    def as_dict(self) -> dict[str, object]:
        return {
            "approval_id": self.approval_id,
            "proposal_id": self.proposal_id,
            "tenant_id": self.tenant_id,
            "assigned_reviewer": self.assigned_reviewer,
            "status": self.status,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "HumanApproval":
        return cls(
            approval_id=str(value["approval_id"]),
            proposal_id=str(value["proposal_id"]),
            tenant_id=str(value["tenant_id"]),
            assigned_reviewer=str(value.get("assigned_reviewer", "")),
            status=str(value.get("status", "pending")),
            reason=str(value.get("reason", "")),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
            expires_at=datetime.fromisoformat(str(value["expires_at"])) if value.get("expires_at") else utc_now(),
            resolved_at=datetime.fromisoformat(str(value["resolved_at"])) if value.get("resolved_at") else None,
        )


class HumanApprovalQueue:
    def __init__(self, persistence: PersistenceStore) -> None:
        self.persistence = persistence

    def request(self, *, proposal_id: str, tenant_id: str, assigned_reviewer: str) -> HumanApproval:
        approval = HumanApproval(proposal_id=proposal_id, tenant_id=tenant_id, assigned_reviewer=assigned_reviewer)
        self.persistence.put("governance_approvals", approval.approval_id, approval.as_dict())
        return approval

    def list(self, tenant_id: str) -> list[HumanApproval]:
        return [HumanApproval.from_dict(item) for item in self.persistence.list_tenant("governance_approvals", tenant_id)]

    def get(self, approval_id: str) -> HumanApproval | None:
        item = self.persistence.get("governance_approvals", approval_id)
        return HumanApproval.from_dict(item) if item else None

    def resolve(self, approval_id: str, *, status: str, reason: str) -> HumanApproval:
        approval = self.get(approval_id)
        if approval is None:
            raise KeyError(approval_id)
        if approval.is_expired():
            raise ConflictError("approval expired")
        if approval.status not in {"pending", "escalated"}:
            raise ConflictError("approval already resolved")
        resolved = HumanApproval(
            approval_id=approval.approval_id,
            proposal_id=approval.proposal_id,
            tenant_id=approval.tenant_id,
            assigned_reviewer=approval.assigned_reviewer,
            status=status,
            reason=reason,
            created_at=approval.created_at,
            expires_at=approval.expires_at,
            resolved_at=utc_now(),
        )
        self.persistence.put("governance_approvals", resolved.approval_id, resolved.as_dict())
        return resolved

    def approved_for_proposal(self, tenant_id: str, proposal_id: str) -> bool:
        return any(approval.proposal_id == proposal_id and approval.status == "approved" for approval in self.list(tenant_id))
