"""Default revenue model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RevenueModel:
    subscription: float = 500.0
    usage_based: float = 0.10
    marketplace: float = 0.30
    package_license: float = 10.0
    federation_delegation: float = 1.0
    enterprise_support: float = 250.0

    def estimate(self, category: str, quantity: float = 1.0) -> float:
        return round(float(getattr(self, category, self.usage_based)) * quantity, 4)
