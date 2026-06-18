"""Deterministic outlier detection for operational metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import mean, pstdev
from uuid import uuid4

from .drift_detection import LOWER_IS_BETTER
from .metrics import AgentMetric


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class AnomalyRecord:
    tenant_id: str
    agent_id: str
    version: str
    metric: str
    expected_value: float
    observed_value: float
    severity: str
    score: float
    anomaly_id: str = field(default_factory=lambda: f"anomaly-{uuid4().hex[:12]}")
    timestamp: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "anomaly_id": self.anomaly_id,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "version": self.version,
            "metric": self.metric,
            "expected_value": self.expected_value,
            "observed_value": self.observed_value,
            "severity": self.severity,
            "score": self.score,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "AnomalyRecord":
        return cls(
            anomaly_id=str(value["anomaly_id"]),
            tenant_id=str(value["tenant_id"]),
            agent_id=str(value["agent_id"]),
            version=str(value.get("version", "unknown")),
            metric=str(value["metric"]),
            expected_value=float(value["expected_value"]),
            observed_value=float(value["observed_value"]),
            severity=str(value["severity"]),
            score=float(value["score"]),
            timestamp=datetime.fromisoformat(str(value["timestamp"])) if value.get("timestamp") else utc_now(),
        )


class AnomalyDetector:
    def detect(self, metrics: list[AgentMetric], *, baseline_size: int = 3) -> list[AnomalyRecord]:
        grouped: dict[tuple[str, str, str, str], list[AgentMetric]] = {}
        for metric in sorted(metrics, key=lambda item: item.timestamp):
            grouped.setdefault((metric.tenant_id, metric.agent_id, metric.version, metric.metric), []).append(metric)
        anomalies: list[AnomalyRecord] = []
        for (tenant_id, agent_id, version, name), records in grouped.items():
            if len(records) <= baseline_size:
                continue
            baseline = [item.value for item in records[:-1]]
            observed = records[-1].value
            expected = mean(baseline)
            deviation = pstdev(baseline) if len(baseline) > 1 else 0.0
            score = abs(observed - expected) / max(deviation, abs(expected) * 0.1, 0.01)
            harmful = observed > expected if name in LOWER_IS_BETTER else observed < expected
            if harmful and score >= 3:
                anomalies.append(
                    AnomalyRecord(
                        tenant_id=tenant_id,
                        agent_id=agent_id,
                        version=version,
                        metric=name,
                        expected_value=round(expected, 4),
                        observed_value=round(observed, 4),
                        severity="critical" if score >= 6 else "major",
                        score=round(score, 4),
                    )
                )
        return anomalies
