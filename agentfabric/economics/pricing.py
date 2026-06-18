"""Pricing policy calculations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PricingPolicy:
    per_seat: float = 20.0
    per_agent: float = 5.0
    per_workflow: float = 0.25
    per_tool_call: float = 0.05
    per_connector: float = 3.0
    per_marketplace_package: float = 2.0
    per_federated_delegation: float = 0.5

    def calculate(self, usage: dict[str, int | float]) -> float:
        return round(
            float(usage.get("seats", 0)) * self.per_seat
            + float(usage.get("agents", 0)) * self.per_agent
            + float(usage.get("workflows", 0)) * self.per_workflow
            + float(usage.get("tool_calls", 0)) * self.per_tool_call
            + float(usage.get("connectors", 0)) * self.per_connector
            + float(usage.get("marketplace_packages", 0)) * self.per_marketplace_package
            + float(usage.get("federated_delegations", 0)) * self.per_federated_delegation,
            4,
        )
