"""Margin analysis."""

from __future__ import annotations

from .cost_tracker import CostTracker
from .revenue_tracker import RevenueTracker
from .unit_economics import UnitEconomics


class MarginAnalyzer:
    def __init__(self, *, costs: CostTracker, revenue: RevenueTracker) -> None:
        self.costs = costs
        self.revenue = revenue

    def tenant_margin(self, tenant_id: str) -> UnitEconomics:
        return UnitEconomics(
            tenant_id=tenant_id,
            total_cost=self.costs.total(tenant_id),
            total_revenue=self.revenue.total(tenant_id),
        )
