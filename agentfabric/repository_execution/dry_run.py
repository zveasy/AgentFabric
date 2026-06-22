"""Dry-run result."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DryRunResult:
    execution_id: str
    tenant_id: str
    status: str
    artifact_count: int
    artifact_hashes: dict[str, str]
    quality_gates: dict[str, bool]

    def as_dict(self) -> dict[str, object]:
        return vars(self)
