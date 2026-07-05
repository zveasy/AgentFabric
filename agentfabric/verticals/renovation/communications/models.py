"""Customer communication models."""

from dataclasses import dataclass

from agentfabric.verticals.renovation.models.base import SerializableModel


@dataclass(frozen=True)
class CustomerMessage(SerializableModel):
    message_id: str
    tenant_id: str
    customer_id: str
    job_id: str
    channel: str
    direction: str
    message_date: str
    subject: str
    body: str
    visibility: str


@dataclass(frozen=True)
class CommunicationRecord(SerializableModel):
    communication_id: str
    tenant_id: str
    lead_id: str
    customer_id: str
    job_id: str
    communication_type: str
    direction: str
    communication_date: str
    summary: str
    visibility: str
    message_id: str = ""
