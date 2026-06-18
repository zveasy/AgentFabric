"""Marketplace license definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class License:
    license_type: str
    seats: int | None = None
    usage_limit: int | None = None
    trial_days: int | None = None
    enterprise_only: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "license_type": self.license_type,
            "seats": self.seats,
            "usage_limit": self.usage_limit,
            "trial_days": self.trial_days,
            "enterprise_only": self.enterprise_only,
        }
