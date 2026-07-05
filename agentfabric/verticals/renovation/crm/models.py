"""Renovation CRM models."""

from dataclasses import dataclass

from agentfabric.verticals.renovation.models.base import SerializableModel


@dataclass(frozen=True)
class Opportunity(SerializableModel):
    opportunity_id: str
    tenant_id: str
    lead_id: str
    customer_id: str
    project_type: str
    expected_value: float
    probability: float
    stage: str
    expected_close_date: str
    weighted_value: float


@dataclass(frozen=True)
class FollowUpTask(SerializableModel):
    follow_up_id: str
    tenant_id: str
    lead_id: str
    opportunity_id: str
    task_type: str
    due_date: str
    description: str
    status: str
    reminder_date: str


@dataclass(frozen=True)
class AppointmentRequest(SerializableModel):
    appointment_id: str
    tenant_id: str
    lead_id: str
    customer_id: str
    requested_date: str
    requested_time: str
    appointment_type: str
    property_address: str
    status: str
    notes: str = ""


@dataclass(frozen=True)
class SiteVisit(SerializableModel):
    site_visit_id: str
    tenant_id: str
    appointment_id: str
    lead_id: str
    customer_id: str
    visit_date: str
    visited_by: str
    summary: str
    next_step: str
