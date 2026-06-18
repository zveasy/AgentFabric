"""Quality gates for promotion and runtime decisions."""

from __future__ import annotations

from dataclasses import dataclass, field

from agentfabric.errors import AuthorizationError

from .scorecard import Scorecard


DEFAULT_GATE_THRESHOLDS = {
    "package_publish": 0.8,
    "package_install": 0.75,
    "agent_runtime_execution": 0.7,
    "workflow_promotion": 0.8,
    "tool_enablement": 0.8,
    "connector_enablement": 0.8,
    "federated_delegation": 0.85,
    "production_deployment": 0.9,
}


@dataclass(frozen=True)
class QualityGate:
    gate_type: str
    threshold: float
    required_metrics: tuple[str, ...] = ()

    def evaluate(self, scorecard: Scorecard) -> bool:
        if scorecard.overall_score < self.threshold:
            return False
        return all(scorecard.metrics.get(metric, 0.0) >= self.threshold for metric in self.required_metrics)


@dataclass
class QualityGateService:
    thresholds: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_GATE_THRESHOLDS))

    def gate(self, gate_type: str, *, threshold: float | None = None, required_metrics: tuple[str, ...] = ()) -> QualityGate:
        return QualityGate(gate_type, threshold if threshold is not None else self.thresholds.get(gate_type, 0.8), required_metrics)

    def enforce(self, gate_type: str, scorecard: Scorecard, *, threshold: float | None = None, required_metrics: tuple[str, ...] = ()) -> None:
        gate = self.gate(gate_type, threshold=threshold, required_metrics=required_metrics)
        if not gate.evaluate(scorecard):
            raise AuthorizationError(f"quality gate failed: {gate_type}")
