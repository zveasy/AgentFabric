"""Domain models generated from the RenovationOS package definition."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class ProjectIntake:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RoomScope:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MaterialSelection:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LaborAssumption:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EstimateLineItem:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EstimateResult:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarginScenario:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskAdjustment:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)
