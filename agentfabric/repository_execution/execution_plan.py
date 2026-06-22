"""Repository execution plan."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .execution_context import ExecutionContext
from .execution_step import ExecutionStep


@dataclass(frozen=True)
class ExecutionPlan:
    execution_id: str
    context: ExecutionContext
    steps: tuple[ExecutionStep, ...]
    artifact_contents: dict[str, str]
    artifact_hashes: dict[str, str]
    quality_gates: dict[str, bool]
    rollback_plan: tuple[str, ...]
    marketplace_metadata: dict[str, object]
    status: str = "planned"

    def as_dict(self, include_contents: bool = False) -> dict[str, object]:
        value = {
            "execution_id": self.execution_id,
            "tenant_id": self.context.tenant_id,
            "context": self.context.as_dict(),
            "steps": [step.as_dict() for step in self.steps],
            "artifact_hashes": dict(sorted(self.artifact_hashes.items())),
            "quality_gates": dict(sorted(self.quality_gates.items())),
            "rollback_plan": list(self.rollback_plan),
            "marketplace_metadata": dict(sorted(self.marketplace_metadata.items())),
            "status": self.status,
        }
        if include_contents:
            value["artifact_contents"] = dict(sorted(self.artifact_contents.items()))
        return value

    @property
    def digest(self) -> str:
        payload = json.dumps(self.as_dict(include_contents=True), sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode()).hexdigest()
