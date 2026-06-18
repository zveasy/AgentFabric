"""Continuous-improvement recommendations backed by operational evidence."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from uuid import uuid4

from .anomaly_detection import AnomalyRecord
from .degradation_monitor import DegradationRecord
from .drift_detection import DriftEvent
from .health import HealthSnapshot
from .version_comparison import VersionComparison


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class ImprovementRecommendation:
    tenant_id: str
    agent_id: str
    version: str
    recommendation_type: str
    rationale: str
    evidence: tuple[str, ...]
    confidence: float
    expected_impact: str
    status: str = "pending"
    approved_by: str | None = None
    recommendation_id: str = field(default_factory=lambda: f"recommendation-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=utc_now)

    def approve(self, principal_id: str) -> "ImprovementRecommendation":
        return replace(self, status="approved", approved_by=principal_id)

    def as_dict(self) -> dict[str, object]:
        return {
            "recommendation_id": self.recommendation_id,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "version": self.version,
            "recommendation_type": self.recommendation_type,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "confidence": self.confidence,
            "expected_impact": self.expected_impact,
            "status": self.status,
            "approved_by": self.approved_by,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "ImprovementRecommendation":
        return cls(
            recommendation_id=str(value["recommendation_id"]),
            tenant_id=str(value["tenant_id"]),
            agent_id=str(value["agent_id"]),
            version=str(value.get("version", "unknown")),
            recommendation_type=str(value["recommendation_type"]),
            rationale=str(value["rationale"]),
            evidence=tuple(str(item) for item in value.get("evidence", ())),
            confidence=float(value["confidence"]),
            expected_impact=str(value["expected_impact"]),
            status=str(value.get("status", "pending")),
            approved_by=str(value["approved_by"]) if value.get("approved_by") else None,
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
        )


class RecommendationEngine:
    def generate(
        self,
        health: HealthSnapshot,
        degradation: DegradationRecord,
        drift: list[DriftEvent],
        anomalies: list[AnomalyRecord],
        comparison: VersionComparison | None = None,
    ) -> ImprovementRecommendation:
        evidence = [*degradation.reasons]
        evidence.extend(f"{event.metric} anomaly score {event.score}" for event in anomalies)
        if comparison:
            evidence.append(f"candidate version is {comparison.result}")
        if degradation.level in {"critical", "major"}:
            kind = "rollback"
            impact = "restore the last known healthy operating profile"
        elif health.dimensions["quality"] < 0.8 or health.dimensions["feedback"] < 0.8:
            kind = "retrain"
            impact = "improve output quality and reduce correction frequency"
        elif comparison and comparison.result == "better":
            kind = "publish"
            impact = "promote the measurably stronger agent version"
        elif health.status == "healthy" and not drift and not anomalies:
            kind = "publish"
            impact = "retain or promote the stable healthy version"
        else:
            kind = "archive"
            impact = "remove an underperforming inactive version from selection"
        confidence = min(0.99, 0.55 + 0.08 * len(evidence) + (0.1 if anomalies else 0.0))
        return ImprovementRecommendation(
            tenant_id=health.tenant_id,
            agent_id=health.agent_id,
            version=health.version,
            recommendation_type=kind,
            rationale=f"{degradation.level} degradation with {health.status} health",
            evidence=tuple(evidence),
            confidence=round(confidence, 4),
            expected_impact=impact,
        )
