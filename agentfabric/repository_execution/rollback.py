"""Rollback planning."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RollbackPlan:
    execution_id: str
    tenant_id: str
    paths: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {"execution_id": self.execution_id, "tenant_id": self.tenant_id, "paths": list(self.paths)}
