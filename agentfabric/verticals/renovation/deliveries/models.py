"""Material delivery models."""

from dataclasses import dataclass

from agentfabric.verticals.renovation.models.base import SerializableModel


@dataclass(frozen=True)
class MaterialDelivery(SerializableModel):
    delivery_id: str
    tenant_id: str
    job_id: str
    schedule_id: str
    phase_id: str
    material: str
    quantity: float
    unit: str
    required_date: str
    expected_date: str
    actual_date: str
    status: str
    supplier_reference: str = ""
