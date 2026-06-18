"""Unit economics summaries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UnitEconomics:
    tenant_id: str
    total_cost: float
    total_revenue: float

    @property
    def gross_margin(self) -> float:
        if self.total_revenue == 0:
            return 0.0
        return round((self.total_revenue - self.total_cost) / self.total_revenue, 4)

    @property
    def profit(self) -> float:
        return round(self.total_revenue - self.total_cost, 4)

    def as_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "total_cost": self.total_cost,
            "total_revenue": self.total_revenue,
            "profit": self.profit,
            "gross_margin": self.gross_margin,
        }
