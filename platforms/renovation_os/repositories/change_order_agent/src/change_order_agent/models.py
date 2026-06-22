"""Domain models generated from the RenovationOS package definition."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class ChangeOrder:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScopeDelta:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CostDelta:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScheduleDelta:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ApprovalStatus:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerApproval:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContractorAcknowledgement:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChangeOrderAuditRecord:
    """Typed domain record with deterministic extension fields."""

    record_id: str
    attributes: dict[str, Any] = field(default_factory=dict)
