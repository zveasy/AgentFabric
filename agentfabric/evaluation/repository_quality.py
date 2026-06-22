"""Repository quality scoring and fail-closed gates."""

from __future__ import annotations

from dataclasses import dataclass

from agentfabric.errors import AuthorizationError


REPOSITORY_QUALITY_METRICS = (
    "architecture_quality",
    "code_quality",
    "test_coverage",
    "documentation_completeness",
    "dependency_health",
    "observability_readiness",
    "security_posture",
)


@dataclass(frozen=True)
class RepositoryQualityScore:
    repository_id: str
    tenant_id: str
    metrics: dict[str, float]

    @property
    def overall_score(self) -> float:
        return round(sum(self.metrics.values()) / len(REPOSITORY_QUALITY_METRICS), 4)

    @property
    def passed(self) -> bool:
        return self.overall_score >= 0.8 and min(self.metrics.values()) >= 0.7

    def as_dict(self) -> dict[str, object]:
        return {
            "repository_id": self.repository_id,
            "tenant_id": self.tenant_id,
            "metrics": dict(sorted(self.metrics.items())),
            "overall_score": self.overall_score,
            "passed": self.passed,
        }


class RepositoryQualityGate:
    def score(self, repository_id: str, tenant_id: str, metrics: dict[str, float]) -> RepositoryQualityScore:
        missing = set(REPOSITORY_QUALITY_METRICS) - set(metrics)
        if missing:
            raise AuthorizationError(f"repository quality evidence missing: {', '.join(sorted(missing))}")
        normalized = {name: float(metrics[name]) for name in REPOSITORY_QUALITY_METRICS}
        if any(value < 0 or value > 1 for value in normalized.values()):
            raise ValueError("repository quality metrics must be between 0 and 1")
        return RepositoryQualityScore(repository_id, tenant_id, normalized)

    def enforce(self, score: RepositoryQualityScore) -> None:
        if not score.passed:
            raise AuthorizationError("repository quality gate failed")
