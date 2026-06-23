"""Renovation change-order models."""

from dataclasses import dataclass

from agentfabric.verticals.renovation.models.base import SerializableModel


@dataclass(frozen=True)
class ChangeOrderLine(SerializableModel):
    description: str
    category: str
    quantity: float
    unit: str
    material_cost: float
    labor_hours: float
    labor_cost: float
    total: float


@dataclass(frozen=True)
class ChangeOrderApproval(SerializableModel):
    approval_id: str
    change_order_id: str
    decision: str
    decision_date: str
    decided_by: str
    reason: str = ""


@dataclass(frozen=True)
class ChangeOrder(SerializableModel):
    change_order_id: str
    tenant_id: str
    job_id: str
    proposal_id: str
    source_type: str
    source_reference: str
    title: str
    description: str
    status: str
    lines: tuple[ChangeOrderLine, ...]
    material_total: float
    labor_total: float
    subtotal: float
    contingency_percentage: float
    contingency: float
    tax_percentage: float
    tax: float
    total_adjustment: float
    schedule_delta_days: int
    template_id: str
    template_version: str
    approval_history: tuple[ChangeOrderApproval, ...]
    rendered_text: str
