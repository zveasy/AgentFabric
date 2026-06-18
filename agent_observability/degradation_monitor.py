"""Quality degradation classification and fail-closed enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from agentfabric.errors import AuthorizationError

from .drift_detection import DriftEvent
from .health import HealthSnapshot


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class DegradationRecord:
    tenant_id: str
    agent_id: str
    version: str
    level: str
    reasons: tuple[str, ...]
    degradation_id: str = field(default_factory=lambda: f"degradation-{uuid4().hex[:12]}")
    timestamp: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "degradation_id": self.degradation_id,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "version": self.version,
            "level": self.level,
            "reasons": list(self.reasons),
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "DegradationRecord":
        return cls(
            degradation_id=str(value["degradation_id"]),
            tenant_id=str(value["tenant_id"]),
            agent_id=str(value["agent_id"]),
            version=str(value.get("version", "unknown")),
            level=str(value["level"]),
            reasons=tuple(str(item) for item in value.get("reasons", ())),
            timestamp=datetime.fromisoformat(str(value["timestamp"])) if value.get("timestamp") else utc_now(),
        )


class DegradationMonitor:
    ORDER = {"none": 0, "minor": 1, "moderate": 2, "major": 3, "critical": 4}

    def assess(self, health: HealthSnapshot, drift: list[DriftEvent]) -> DegradationRecord:
        level = {"healthy": "none", "warning": "minor", "degraded": "major", "critical": "critical"}[health.status]
        reasons = [f"health is {health.status}"]
        for event in drift:
            if self.ORDER.get(event.severity, 0) > self.ORDER[level]:
                level = event.severity
            reasons.append(f"{event.metric} drift is {event.severity}")
        return DegradationRecord(
            tenant_id=health.tenant_id,
            agent_id=health.agent_id,
            version=health.version,
            level=level,
            reasons=tuple(reasons),
        )

    def enforce(self, degradation: DegradationRecord, *, maximum: str = "moderate") -> None:
        if self.ORDER[degradation.level] > self.ORDER[maximum]:
            raise AuthorizationError(f"agent quality degraded: {degradation.level}")
