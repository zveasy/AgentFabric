"""Baseline-based quality drift detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import mean
from uuid import uuid4

from .metrics import AgentMetric


LOWER_IS_BETTER = {"latency", "cost", "tool_failures", "retries", "hallucination_rate", "correction_frequency", "token_usage"}


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class DriftEvent:
    tenant_id: str
    agent_id: str
    version: str
    metric: str
    baseline: float
    current_value: float
    severity: str
    change_ratio: float
    drift_id: str = field(default_factory=lambda: f"drift-{uuid4().hex[:12]}")
    timestamp: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "drift_id": self.drift_id,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "version": self.version,
            "metric": self.metric,
            "baseline": self.baseline,
            "current_value": self.current_value,
            "severity": self.severity,
            "change_ratio": self.change_ratio,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "DriftEvent":
        return cls(
            drift_id=str(value["drift_id"]),
            tenant_id=str(value["tenant_id"]),
            agent_id=str(value["agent_id"]),
            version=str(value.get("version", "unknown")),
            metric=str(value["metric"]),
            baseline=float(value["baseline"]),
            current_value=float(value["current_value"]),
            severity=str(value["severity"]),
            change_ratio=float(value.get("change_ratio", 0.0)),
            timestamp=datetime.fromisoformat(str(value["timestamp"])) if value.get("timestamp") else utc_now(),
        )


class DriftDetector:
    def detect(self, metrics: list[AgentMetric], *, baseline_size: int = 3, current_size: int = 1) -> list[DriftEvent]:
        grouped: dict[tuple[str, str, str, str], list[AgentMetric]] = {}
        for metric in sorted(metrics, key=lambda item: item.timestamp):
            grouped.setdefault((metric.tenant_id, metric.agent_id, metric.version, metric.metric), []).append(metric)
        events: list[DriftEvent] = []
        for (tenant_id, agent_id, version, name), records in grouped.items():
            if len(records) < baseline_size + current_size:
                continue
            baseline = mean(item.value for item in records[:baseline_size])
            current = mean(item.value for item in records[-current_size:])
            ratio = _deterioration_ratio(name, baseline, current)
            severity = _severity(ratio)
            if severity:
                events.append(
                    DriftEvent(
                        tenant_id=tenant_id,
                        agent_id=agent_id,
                        version=version,
                        metric=name,
                        baseline=round(baseline, 4),
                        current_value=round(current, 4),
                        severity=severity,
                        change_ratio=round(ratio, 4),
                    )
                )
        return events


def _deterioration_ratio(metric: str, baseline: float, current: float) -> float:
    denominator = max(abs(baseline), 0.01)
    return (current - baseline) / denominator if metric in LOWER_IS_BETTER else (baseline - current) / denominator


def _severity(ratio: float) -> str | None:
    if ratio >= 0.5:
        return "critical"
    if ratio >= 0.3:
        return "major"
    if ratio >= 0.2:
        return "moderate"
    if ratio >= 0.1:
        return "minor"
    return None
