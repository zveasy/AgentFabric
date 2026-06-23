"""Proposal models."""

from dataclasses import dataclass

from .base import SerializableModel
from .customer_models import Customer, Project
from .estimate_models import Estimate


@dataclass(frozen=True)
class PaymentSchedule(SerializableModel):
    label: str
    percentage: float
    amount: float


@dataclass(frozen=True)
class Timeline(SerializableModel):
    phase: str
    duration_days: int
    sequence: int


@dataclass(frozen=True)
class Proposal(SerializableModel):
    proposal_id: str
    tenant_id: str
    customer: Customer
    project: Project
    estimate: Estimate
    template_id: str
    template_version: str
    style: str
    scope_of_work: tuple[str, ...]
    payment_schedule: tuple[PaymentSchedule, ...]
    timeline: tuple[Timeline, ...]
    warranty: str
    terms_and_conditions: tuple[str, ...]
    rendered_text: str
