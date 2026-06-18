"""Federation trust agreements."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class TrustAgreement:
    tenant_id: str
    organization_id: str
    remote_org_id: str
    created_by: str
    allowed_capabilities: tuple[str, ...] = ()
    denied_capabilities: tuple[str, ...] = ()
    permitted_data_classes: tuple[str, ...] = ("public", "internal")
    allowed_workflow_types: tuple[str, ...] = ()
    status: str = "draft"
    agreement_id: str = field(default_factory=lambda: f"fed-agree-{uuid4().hex[:12]}")
    expires_at: datetime = field(default_factory=lambda: utc_now() + timedelta(days=30))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    revoked_reason: str = ""

    def is_active(self) -> bool:
        return self.status == "active" and utc_now() < self.expires_at

    def is_expired(self) -> bool:
        return utc_now() >= self.expires_at

    def allows_capability(self, capability: str) -> bool:
        if capability in self.denied_capabilities:
            return False
        return not self.allowed_capabilities or capability in self.allowed_capabilities

    def with_status(self, status: str, reason: str = "") -> "TrustAgreement":
        return TrustAgreement(
            agreement_id=self.agreement_id,
            tenant_id=self.tenant_id,
            organization_id=self.organization_id,
            remote_org_id=self.remote_org_id,
            created_by=self.created_by,
            allowed_capabilities=self.allowed_capabilities,
            denied_capabilities=self.denied_capabilities,
            permitted_data_classes=self.permitted_data_classes,
            allowed_workflow_types=self.allowed_workflow_types,
            status=status,
            expires_at=self.expires_at,
            created_at=self.created_at,
            updated_at=utc_now(),
            revoked_reason=reason,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "agreement_id": self.agreement_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "remote_org_id": self.remote_org_id,
            "created_by": self.created_by,
            "allowed_capabilities": list(self.allowed_capabilities),
            "denied_capabilities": list(self.denied_capabilities),
            "permitted_data_classes": list(self.permitted_data_classes),
            "allowed_workflow_types": list(self.allowed_workflow_types),
            "status": self.status,
            "expires_at": self.expires_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "revoked_reason": self.revoked_reason,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "TrustAgreement":
        return cls(
            agreement_id=str(value["agreement_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            remote_org_id=str(value["remote_org_id"]),
            created_by=str(value.get("created_by", "")),
            allowed_capabilities=tuple(str(item) for item in value.get("allowed_capabilities", ())),
            denied_capabilities=tuple(str(item) for item in value.get("denied_capabilities", ())),
            permitted_data_classes=tuple(str(item) for item in value.get("permitted_data_classes", ("public", "internal"))),
            allowed_workflow_types=tuple(str(item) for item in value.get("allowed_workflow_types", ())),
            status=str(value.get("status", "draft")),
            expires_at=datetime.fromisoformat(str(value["expires_at"])) if value.get("expires_at") else utc_now(),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
            updated_at=datetime.fromisoformat(str(value["updated_at"])) if value.get("updated_at") else utc_now(),
            revoked_reason=str(value.get("revoked_reason", "")),
        )
