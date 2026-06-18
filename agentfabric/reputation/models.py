"""Agent reputation metrics and scoring."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReputationRecord:
    agent_id: str
    successful_tasks: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0
    human_ratings_total: float = 0.0
    human_ratings_count: int = 0
    approvals: int = 0
    approval_requests: int = 0

    @property
    def total_tasks(self) -> int:
        return self.successful_tasks + self.failures

    @property
    def average_latency_ms(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.total_latency_ms / self.total_tasks

    @property
    def reliability(self) -> float:
        if self.total_tasks == 0:
            return 1.0
        return self.successful_tasks / self.total_tasks

    @property
    def approval_rate(self) -> float:
        if self.approval_requests == 0:
            return 1.0
        return self.approvals / self.approval_requests

    @property
    def average_human_rating(self) -> float:
        if self.human_ratings_count == 0:
            return 0.0
        return self.human_ratings_total / self.human_ratings_count

    @property
    def health_score(self) -> float:
        latency_penalty = min(self.average_latency_ms / 10000.0, 0.4)
        return round(max(0.0, self.reliability - latency_penalty), 4)

    @property
    def reputation_score(self) -> float:
        rating_score = self.average_human_rating / 5 if self.human_ratings_count else 0.8
        return round((self.reliability * 0.5) + (self.approval_rate * 0.2) + (rating_score * 0.3), 4)

    @property
    def confidence_score(self) -> float:
        sample_weight = min(self.total_tasks / 20.0, 1.0)
        return round(self.reputation_score * (0.5 + sample_weight / 2), 4)

    def as_dict(self) -> dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "successful_tasks": self.successful_tasks,
            "failures": self.failures,
            "average_latency_ms": self.average_latency_ms,
            "reliability": self.reliability,
            "human_ratings": self.average_human_rating,
            "approval_rate": self.approval_rate,
            "health_score": self.health_score,
            "reputation_score": self.reputation_score,
            "confidence_score": self.confidence_score,
        }
