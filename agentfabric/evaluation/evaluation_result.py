"""Evaluation run results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


QUALITY_METRICS = (
    "correctness",
    "completeness",
    "latency",
    "cost",
    "safety",
    "policy_compliance",
    "tenant_isolation_compliance",
    "veil_boundary_compliance",
    "human_approval_accuracy",
    "hallucination_risk",
    "tool_use_accuracy",
)


@dataclass(frozen=True)
class EvaluationResult:
    dataset_id: str
    tenant_id: str
    target_type: str
    target_id: str
    metrics: dict[str, float]
    case_results: list[dict[str, object]]
    run_id: str = field(default_factory=lambda: f"eval-run-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=utc_now)

    @property
    def overall_score(self) -> float:
        if not self.metrics:
            return 0.0
        return round(sum(self.metrics.values()) / len(self.metrics), 4)

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "dataset_id": self.dataset_id,
            "tenant_id": self.tenant_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "metrics": dict(self.metrics),
            "overall_score": self.overall_score,
            "case_results": list(self.case_results),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "EvaluationResult":
        return cls(
            run_id=str(value["run_id"]),
            dataset_id=str(value["dataset_id"]),
            tenant_id=str(value["tenant_id"]),
            target_type=str(value["target_type"]),
            target_id=str(value["target_id"]),
            metrics={str(key): float(item) for key, item in dict(value.get("metrics", {})).items()},
            case_results=list(value.get("case_results", [])),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
        )
