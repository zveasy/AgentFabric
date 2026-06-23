"""Estimate models."""

from dataclasses import dataclass

from .base import SerializableModel
from .scope_models import ScopeItem


@dataclass(frozen=True)
class MaterialLine(SerializableModel):
    description: str
    category: str
    quantity: float
    unit: str
    unit_rate: float
    total: float


@dataclass(frozen=True)
class LaborLine(SerializableModel):
    description: str
    hours: float
    hourly_rate: float
    total: float


@dataclass(frozen=True)
class Estimate(SerializableModel):
    estimate_id: str
    tenant_id: str
    project_id: str
    scope_description: str
    scope_items: tuple[ScopeItem, ...]
    material_lines: tuple[MaterialLine, ...]
    labor_lines: tuple[LaborLine, ...]
    material_total: float
    labor_total: float
    subtotal: float
    contingency_percentage: float
    contingency: float
    taxable_amount: float
    tax_percentage: float
    tax: float
    total: float
    notes: str
    rate_table_version: str = "renovation-rates-v1"
