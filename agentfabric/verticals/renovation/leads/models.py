"""Renovation lead intake models."""

from dataclasses import dataclass

from agentfabric.verticals.renovation.models.base import SerializableModel


@dataclass(frozen=True)
class LeadSource(SerializableModel):
    source_type: str
    source_name: str
    campaign: str = ""
    referral_name: str = ""


@dataclass(frozen=True)
class Lead(SerializableModel):
    lead_id: str
    tenant_id: str
    name: str
    email: str
    phone: str
    property_address: str
    project_type: str
    description: str
    status: str
    source: LeadSource
    created_date: str
    last_contact_date: str = ""
    lost_reason: str = ""
    customer_id: str = ""
