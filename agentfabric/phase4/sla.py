"""SLA and support tier definitions."""

from __future__ import annotations

from dataclasses import dataclass

from agentfabric.errors import NotFoundError


@dataclass(frozen=True)
class SupportTier:
    name: str
    availability_target_percent: float
    response_time_minutes: int
    escalation_policy: str


class SlaCatalog:
    """Catalog for enterprise support tiers."""

    def __init__(self) -> None:
        self._tiers = {
            "standard": SupportTier(
                name="standard",
                availability_target_percent=99.5,
                response_time_minutes=240,
                escalation_policy="business-hours",
            ),
            "premium": SupportTier(
                name="premium",
                availability_target_percent=99.9,
                response_time_minutes=60,
                escalation_policy="24x7",
            ),
        }

    def get_tier(self, name: str) -> SupportTier:
        tier = self._tiers.get(name)
        if tier is None:
            raise NotFoundError(f"unknown SLA tier: {name}")
        return tier
