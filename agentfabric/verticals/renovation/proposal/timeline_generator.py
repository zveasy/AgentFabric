"""Ordered, date-independent project timeline generation."""

from agentfabric.verticals.renovation.models import Timeline


class TimelineGenerator:
    def build(self, phases: list[dict[str, object]]) -> tuple[Timeline, ...]:
        return tuple(
            Timeline(str(item["phase"]), int(item["duration_days"]), index)
            for index, item in enumerate(phases, start=1)
        )
