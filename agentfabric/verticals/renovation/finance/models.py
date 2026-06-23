"""Renovation job finance models."""

from dataclasses import dataclass

from agentfabric.verticals.renovation.models.base import SerializableModel


@dataclass(frozen=True)
class ActualMaterialCost(SerializableModel):
    description: str
    quantity: float
    unit: str
    unit_cost: float
    amount: float


@dataclass(frozen=True)
class ActualLaborCost(SerializableModel):
    description: str
    hours: float
    hourly_rate: float
    amount: float


@dataclass(frozen=True)
class SubcontractorCost(SerializableModel):
    vendor: str
    description: str
    amount: float


@dataclass(frozen=True)
class OverheadAllocation(SerializableModel):
    description: str
    allocation_method: str
    amount: float


@dataclass(frozen=True)
class JobCostRecord(SerializableModel):
    cost_record_id: str
    tenant_id: str
    job_id: str
    cost_date: str
    category: str
    description: str
    amount: float
    source_reference: str
    material: ActualMaterialCost | None = None
    labor: ActualLaborCost | None = None
    subcontractor: SubcontractorCost | None = None
    overhead: OverheadAllocation | None = None
