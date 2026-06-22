"""Domain models generated from the RenovationOS package definition."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class ContractorProfile:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CrewAssignment:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JobTask:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AttendanceRecord:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QualityIssue:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LicenseDocument:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InsuranceDocument:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaymentMilestone:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)
