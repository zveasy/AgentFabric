"""Explicit approval gate for repository writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from agentfabric.errors import AuthorizationError
from agentfabric.persistence import PersistenceStore


@dataclass(frozen=True)
class ApprovalRecord:
    execution_id: str
    tenant_id: str
    approved_by: str
    approved_at: str
    plan_digest: str

    def as_dict(self) -> dict[str, str]:
        return vars(self)


class ApprovalGate:
    def __init__(self, persistence: PersistenceStore) -> None:
        self.persistence = persistence

    def approve(self, execution_id: str, tenant_id: str, principal_id: str, plan_digest: str) -> ApprovalRecord:
        record = ApprovalRecord(
            execution_id=execution_id,
            tenant_id=tenant_id,
            approved_by=principal_id,
            approved_at=datetime.now(tz=timezone.utc).isoformat(),
            plan_digest=plan_digest,
        )
        self.persistence.put("factory_execution_approvals", execution_id, record.as_dict())
        return record

    def require(self, execution_id: str, tenant_id: str, plan_digest: str) -> ApprovalRecord:
        value = self.persistence.get("factory_execution_approvals", execution_id)
        if value is None:
            raise AuthorizationError("repository execution approval is required")
        if value.get("tenant_id") != tenant_id or value.get("plan_digest") != plan_digest:
            raise AuthorizationError("repository execution approval is invalid")
        return ApprovalRecord(**{key: str(item) for key, item in value.items()})
