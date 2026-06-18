"""Default runtime cost model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    agent_run: float = 0.02
    workflow_run: float = 0.08
    tool_execution: float = 0.03
    connector_sync: float = 0.04
    marketplace_execution: float = 0.025
    federation_delegation: float = 0.05
    evaluation_run: float = 0.02
    storage_gb_month: float = 0.10
    queue_worker_runtime: float = 0.01
    audit_bundle_export: float = 0.02

    def estimate(self, category: str, quantity: float = 1.0) -> float:
        return round(float(getattr(self, category, self.queue_worker_runtime)) * quantity, 4)
