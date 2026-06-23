"""Deterministic proposal scope formatting."""

from agentfabric.verticals.renovation.models import Estimate


class ScopeFormatter:
    def format(self, estimate: Estimate) -> tuple[str, ...]:
        return tuple(
            f"{index}. {item.description} ({item.quantity:g} {item.unit})"
            for index, item in enumerate(estimate.scope_items, start=1)
        )
