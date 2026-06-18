"""Usage aggregation helpers."""

from __future__ import annotations

from .usage_event import UsageEvent


def aggregate_usage(events: list[UsageEvent]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for event in events:
        totals[event.event_type] = totals.get(event.event_type, 0) + event.quantity
    return totals
