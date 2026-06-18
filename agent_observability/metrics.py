"""Tenant-scoped operational metrics for agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


SUPPORTED_METRICS = {
    "latency",
    "token_usage",
    "cost",
    "tool_failures",
    "retries",
    "hallucination_rate",
    "evaluation_score",
    "user_rating",
    "correction_frequency",
    "reliability",
}


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class AgentMetric:
    tenant_id: str
    agent_id: str
    metric: str
    value: float
    version: str = "unknown"
    metadata: dict[str, object] = field(default_factory=dict)
    metric_id: str = field(default_factory=lambda: f"agent-metric-{uuid4().hex[:12]}")
    timestamp: datetime = field(default_factory=utc_now)

    def validate(self) -> None:
        if not self.tenant_id or not self.agent_id:
            raise ValueError("tenant_id and agent_id are required")
        if self.metric not in SUPPORTED_METRICS:
            raise ValueError(f"unsupported agent metric: {self.metric}")
        if self.value < 0:
            raise ValueError("metric value cannot be negative")
        if self.metric in {"hallucination_rate", "correction_frequency", "reliability", "evaluation_score"} and self.value > 1:
            raise ValueError(f"{self.metric} must be between 0 and 1")
        if self.metric == "user_rating" and self.value > 5:
            raise ValueError("user_rating must be between 0 and 5")

    def as_dict(self) -> dict[str, object]:
        return {
            "metric_id": self.metric_id,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "version": self.version,
            "metric": self.metric,
            "value": self.value,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "AgentMetric":
        return cls(
            metric_id=str(value["metric_id"]),
            tenant_id=str(value["tenant_id"]),
            agent_id=str(value["agent_id"]),
            version=str(value.get("version", "unknown")),
            metric=str(value["metric"]),
            value=float(value["value"]),
            metadata=dict(value.get("metadata", {})),
            timestamp=datetime.fromisoformat(str(value["timestamp"])) if value.get("timestamp") else utc_now(),
        )
