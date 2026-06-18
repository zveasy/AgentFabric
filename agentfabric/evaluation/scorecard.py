"""Evaluation scorecards."""

from __future__ import annotations

from dataclasses import dataclass

from .evaluation_result import EvaluationResult


@dataclass(frozen=True)
class Scorecard:
    run_id: str
    tenant_id: str
    target_type: str
    target_id: str
    metrics: dict[str, float]
    overall_score: float
    passed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "metrics": dict(self.metrics),
            "overall_score": self.overall_score,
            "passed": self.passed,
        }

    @classmethod
    def from_result(cls, result: EvaluationResult, *, threshold: float = 0.8) -> "Scorecard":
        return cls(
            run_id=result.run_id,
            tenant_id=result.tenant_id,
            target_type=result.target_type,
            target_id=result.target_id,
            metrics=dict(result.metrics),
            overall_score=result.overall_score,
            passed=result.overall_score >= threshold,
        )
