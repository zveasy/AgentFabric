"""Offline material estimation with fixed local rates."""

from agentfabric.verticals.renovation.models import MaterialLine, ScopeItem


DEFAULT_MATERIAL_RATES = {
    "cabinetry": 350.0,
    "flooring": 8.5,
    "painting": 2.25,
    "drywall": 3.5,
    "tile": 12.0,
    "fixtures": 225.0,
    "demolition": 4.0,
    "general": 75.0,
}


class MaterialEstimator:
    def estimate(
        self,
        items: tuple[ScopeItem, ...],
        rates: dict[str, float] | None = None,
    ) -> tuple[MaterialLine, ...]:
        rate_table = {**DEFAULT_MATERIAL_RATES, **(rates or {})}
        lines = []
        for item in items:
            if item.category not in rate_table or rate_table[item.category] < 0:
                raise ValueError(f"material rate unavailable for {item.category}")
            rate = round(float(rate_table[item.category]), 2)
            lines.append(
                MaterialLine(
                    item.description,
                    item.category,
                    item.quantity,
                    item.unit,
                    rate,
                    round(item.quantity * rate, 2),
                )
            )
        return tuple(lines)
