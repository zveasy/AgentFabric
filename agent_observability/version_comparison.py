"""Explainable agent version comparisons."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import mean
from uuid import uuid4

from .drift_detection import LOWER_IS_BETTER
from .metrics import AgentMetric


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class VersionComparison:
    tenant_id: str
    agent_id: str
    baseline_version: str
    candidate_version: str
    result: str
    metrics_delta: dict[str, float]
    score_delta: float
    latency_delta: float
    cost_delta: float
    explanation: tuple[str, ...]
    recommendation: str
    comparison_id: str = field(default_factory=lambda: f"comparison-{uuid4().hex[:12]}")
    timestamp: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "comparison_id": self.comparison_id,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "baseline_version": self.baseline_version,
            "candidate_version": self.candidate_version,
            "result": self.result,
            "metrics_delta": dict(self.metrics_delta),
            "score_delta": self.score_delta,
            "latency_delta": self.latency_delta,
            "cost_delta": self.cost_delta,
            "explanation": list(self.explanation),
            "recommendation": self.recommendation,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "VersionComparison":
        return cls(
            comparison_id=str(value["comparison_id"]),
            tenant_id=str(value["tenant_id"]),
            agent_id=str(value["agent_id"]),
            baseline_version=str(value["baseline_version"]),
            candidate_version=str(value["candidate_version"]),
            result=str(value["result"]),
            metrics_delta={str(key): float(item) for key, item in dict(value.get("metrics_delta", {})).items()},
            score_delta=float(value.get("score_delta", 0.0)),
            latency_delta=float(value.get("latency_delta", 0.0)),
            cost_delta=float(value.get("cost_delta", 0.0)),
            explanation=tuple(str(item) for item in value.get("explanation", ())),
            recommendation=str(value.get("recommendation", "hold")),
            timestamp=datetime.fromisoformat(str(value["timestamp"])) if value.get("timestamp") else utc_now(),
        )


class VersionComparator:
    def compare(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        baseline_version: str,
        candidate_version: str,
        metrics: list[AgentMetric],
    ) -> VersionComparison:
        baseline = _aggregate(metrics, baseline_version)
        candidate = _aggregate(metrics, candidate_version)
        names = sorted(set(baseline) | set(candidate))
        deltas = {name: round(candidate.get(name, 0.0) - baseline.get(name, 0.0), 4) for name in names}
        impacts = []
        explanation = []
        for name in names:
            delta = deltas[name]
            impact = -delta if name in LOWER_IS_BETTER else delta
            impacts.append(impact / max(abs(baseline.get(name, 0.0)), 1.0))
            if abs(delta) >= 0.0001:
                explanation.append(f"{name} changed by {delta:+.4f}")
        score_delta = deltas.get("evaluation_score", 0.0)
        overall = mean(impacts) if impacts else 0.0
        result = "better" if overall > 0.02 else "worse" if overall < -0.02 else "same"
        recommendation = {"better": "publish", "same": "hold", "worse": "rollback"}[result]
        return VersionComparison(
            tenant_id=tenant_id,
            agent_id=agent_id,
            baseline_version=baseline_version,
            candidate_version=candidate_version,
            result=result,
            metrics_delta=deltas,
            score_delta=round(score_delta, 4),
            latency_delta=deltas.get("latency", 0.0),
            cost_delta=deltas.get("cost", 0.0),
            explanation=tuple(explanation) or ("no material metric differences",),
            recommendation=recommendation,
        )


def _aggregate(metrics: list[AgentMetric], version: str) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for metric in metrics:
        if metric.version == version:
            grouped.setdefault(metric.metric, []).append(metric.value)
    if not grouped:
        raise ValueError(f"no metrics for version {version}")
    return {name: mean(values) for name, values in grouped.items()}
