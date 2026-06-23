"""Offline labor estimation with fixed productivity assumptions."""

from agentfabric.verticals.renovation.models import LaborLine, ScopeItem


DEFAULT_LABOR_HOURS = {
    "cabinetry": 6.0,
    "flooring": 0.08,
    "painting": 0.04,
    "drywall": 0.06,
    "tile": 0.12,
    "fixtures": 2.0,
    "demolition": 0.05,
    "general": 1.0,
}


class LaborEstimator:
    def estimate(
        self,
        items: tuple[ScopeItem, ...],
        hourly_rate: float,
        hours: dict[str, float] | None = None,
    ) -> tuple[LaborLine, ...]:
        if hourly_rate <= 0:
            raise ValueError("labor rate must be positive")
        assumptions = {**DEFAULT_LABOR_HOURS, **(hours or {})}
        lines = []
        for item in items:
            if item.category not in assumptions or assumptions[item.category] < 0:
                raise ValueError(f"labor assumption unavailable for {item.category}")
            calculated_hours = round(item.quantity * float(assumptions[item.category]), 2)
            lines.append(
                LaborLine(
                    item.description,
                    calculated_hours,
                    round(hourly_rate, 2),
                    round(calculated_hours * hourly_rate, 2),
                )
            )
        return tuple(lines)
