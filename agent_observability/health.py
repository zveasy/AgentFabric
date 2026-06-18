"""Agent health scoring with explainable dimensions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import mean
from uuid import uuid4

from .metrics import AgentMetric


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class HealthSnapshot:
    tenant_id: str
    agent_id: str
    version: str
    status: str
    score: float
    dimensions: dict[str, float]
    evidence: dict[str, object] = field(default_factory=dict)
    snapshot_id: str = field(default_factory=lambda: f"health-{uuid4().hex[:12]}")
    timestamp: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "version": self.version,
            "status": self.status,
            "score": self.score,
            "dimensions": dict(self.dimensions),
            "evidence": dict(self.evidence),
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "HealthSnapshot":
        return cls(
            snapshot_id=str(value["snapshot_id"]),
            tenant_id=str(value["tenant_id"]),
            agent_id=str(value["agent_id"]),
            version=str(value.get("version", "unknown")),
            status=str(value["status"]),
            score=float(value["score"]),
            dimensions={str(key): float(item) for key, item in dict(value.get("dimensions", {})).items()},
            evidence=dict(value.get("evidence", {})),
            timestamp=datetime.fromisoformat(str(value["timestamp"])) if value.get("timestamp") else utc_now(),
        )


class HealthEngine:
    def compute(self, tenant_id: str, agent_id: str, version: str, metrics: list[AgentMetric]) -> HealthSnapshot:
        grouped: dict[str, list[float]] = {}
        for metric in metrics:
            grouped.setdefault(metric.metric, []).append(metric.value)

        quality = _average(grouped.get("evaluation_score"), 1.0)
        latency_ms = _average(grouped.get("latency"), 0.0)
        latency = _lower_is_better_score(latency_ms, warning=1000, degraded=2500, critical=5000)
        failure_rate = _average(grouped.get("tool_failures"), 0.0)
        retry_rate = _average(grouped.get("retries"), 0.0)
        explicit_reliability = _average(grouped.get("reliability"), 1.0)
        reliability = min(explicit_reliability, max(0.0, 1.0 - min(1.0, failure_rate * 0.2 + retry_rate * 0.1)))
        cost = _lower_is_better_score(_average(grouped.get("cost"), 0.0), warning=1.0, degraded=5.0, critical=20.0)
        rating = _average(grouped.get("user_rating"), 5.0) / 5.0
        corrections = _average(grouped.get("correction_frequency"), 0.0)
        hallucinations = _average(grouped.get("hallucination_rate"), 0.0)
        feedback = max(0.0, min(rating, 1.0 - corrections))
        quality = max(0.0, min(quality, 1.0 - hallucinations))

        dimensions = {
            "quality": round(quality, 4),
            "latency": round(latency, 4),
            "reliability": round(reliability, 4),
            "cost": round(cost, 4),
            "feedback": round(feedback, 4),
        }
        score = round(sum(dimensions.values()) / len(dimensions), 4)
        status = _health_status(score, min(dimensions.values()))
        return HealthSnapshot(
            tenant_id=tenant_id,
            agent_id=agent_id,
            version=version,
            status=status,
            score=score,
            dimensions=dimensions,
            evidence={"metric_count": len(metrics), "metrics": {key: len(values) for key, values in grouped.items()}},
        )


def _average(values: list[float] | None, default: float) -> float:
    return mean(values) if values else default


def _lower_is_better_score(value: float, *, warning: float, degraded: float, critical: float) -> float:
    if value <= warning:
        return 1.0
    if value <= degraded:
        return 0.75
    if value <= critical:
        return 0.5
    return 0.2


def _health_status(score: float, weakest: float) -> str:
    if score < 0.45 or weakest < 0.25:
        return "critical"
    if score < 0.65 or weakest < 0.6:
        return "degraded"
    if score < 0.85 or weakest < 0.85:
        return "warning"
    return "healthy"
