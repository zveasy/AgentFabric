"""Renovation receivable and payable models."""

from dataclasses import dataclass

from agentfabric.verticals.renovation.models.base import SerializableModel


@dataclass(frozen=True)
class PaymentRecord(SerializableModel):
    payment_id: str
    tenant_id: str
    target_type: str
    target_id: str
    payment_date: str
    amount: float
    method: str
    reference: str


@dataclass(frozen=True)
class Invoice(SerializableModel):
    invoice_id: str
    tenant_id: str
    job_id: str
    customer_id: str
    invoice_date: str
    due_date: str
    description: str
    amount: float
    tax: float
    total: float
    paid_amount: float
    outstanding_balance: float
    status: str
    payment_records: tuple[PaymentRecord, ...]


@dataclass(frozen=True)
class VendorPayable(SerializableModel):
    payable_id: str
    tenant_id: str
    job_id: str
    vendor: str
    payable_date: str
    due_date: str
    description: str
    amount: float
    paid_amount: float
    outstanding_balance: float
    status: str
    payment_records: tuple[PaymentRecord, ...]
