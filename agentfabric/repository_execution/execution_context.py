"""Tenant-scoped repository execution context."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionContext:
    tenant_id: str
    organization_id: str
    principal_id: str
    platform_id: str
    repository_id: str
    blueprint_version: str
    knowledge_pack_version: str

    def as_dict(self) -> dict[str, str]:
        return vars(self)
