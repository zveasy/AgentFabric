"""Repository execution result."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionResult:
    execution_id: str
    tenant_id: str
    status: str
    artifact_hashes: dict[str, str]
    approval: dict[str, object]
    rollback_plan: tuple[str, ...]
    marketplace_metadata: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "execution_id": self.execution_id,
            "tenant_id": self.tenant_id,
            "status": self.status,
            "artifact_hashes": dict(sorted(self.artifact_hashes.items())),
            "approval": self.approval,
            "rollback_plan": list(self.rollback_plan),
            "marketplace_metadata": self.marketplace_metadata,
        }
