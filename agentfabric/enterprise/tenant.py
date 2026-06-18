"""Enterprise tenant model and service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from agentfabric.persistence import PersistenceStore


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class Tenant:
    tenant_id: str
    organization_id: str
    name: str
    created_by: str
    billing_plan: str = "dev"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "name": self.name,
            "billing_plan": self.billing_plan,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "Tenant":
        return cls(
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            name=str(value["name"]),
            billing_plan=str(value.get("billing_plan", "dev")),
            created_by=str(value["created_by"]),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            updated_at=datetime.fromisoformat(str(value["updated_at"])),
        )


class TenantService:
    def __init__(self, persistence: PersistenceStore) -> None:
        self.persistence = persistence
        self.persistence.initialize()

    def create_tenant(
        self,
        *,
        tenant_id: str,
        organization_id: str,
        name: str,
        created_by: str,
        billing_plan: str = "dev",
    ) -> Tenant:
        if self.persistence.get("tenants", tenant_id) is not None:
            raise ValueError("tenant already exists")
        tenant = Tenant(
            tenant_id=tenant_id,
            organization_id=organization_id,
            name=name,
            created_by=created_by,
            billing_plan=billing_plan,
        )
        self.persistence.put("tenants", tenant_id, tenant.as_dict())
        return tenant

    def get(self, tenant_id: str) -> Tenant | None:
        item = self.persistence.get("tenants", tenant_id)
        return Tenant.from_dict(item) if item else None

    def list_for_principal(self, principal_tenant_id: str, *, global_admin: bool = False) -> list[Tenant]:
        items = self.persistence.list("tenants") if global_admin else self.persistence.list_tenant("tenants", principal_tenant_id)
        if not items and self.get(principal_tenant_id) is not None:
            item = self.persistence.get("tenants", principal_tenant_id)
            items = [item] if item else []
        return [Tenant.from_dict(item) for item in items]

    def update_billing_plan(self, tenant_id: str, plan: str) -> Tenant:
        tenant = self.get(tenant_id)
        if tenant is None:
            raise KeyError("tenant not found")
        tenant.billing_plan = plan
        tenant.updated_at = utc_now()
        self.persistence.put("tenants", tenant_id, tenant.as_dict())
        return tenant
