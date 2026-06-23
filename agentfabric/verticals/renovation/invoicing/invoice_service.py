"""Deterministic invoice, payment, and payable handling."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from hashlib import sha256
import json

from .models import Invoice, PaymentRecord, VendorPayable


class InvoiceService:
    def create_invoice(
        self,
        tenant_id: str,
        job_id: str,
        customer_id: str,
        payload: dict[str, object],
    ) -> Invoice:
        invoice_date = _date(payload["invoice_date"])
        due_date = _date(payload["due_date"])
        if due_date < invoice_date:
            raise ValueError("invoice due date precedes invoice date")
        amount = _positive_money(payload["amount"], "invoice amount")
        tax = _non_negative_money(payload.get("tax", 0), "invoice tax")
        total = _money(amount + tax)
        identity = {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "customer_id": customer_id,
            "invoice_date": invoice_date.isoformat(),
            "due_date": due_date.isoformat(),
            "description": str(payload["description"]).strip(),
            "amount": amount,
            "tax": tax,
        }
        if not identity["description"]:
            raise ValueError("invoice description is required")
        return Invoice(
            invoice_id=f"invoice-{_digest(identity)[:20]}",
            total=total,
            paid_amount=0.0,
            outstanding_balance=total,
            status="open",
            payment_records=(),
            **identity,
        )

    def create_payable(
        self,
        tenant_id: str,
        job_id: str,
        payload: dict[str, object],
    ) -> VendorPayable:
        payable_date = _date(payload["payable_date"])
        due_date = _date(payload["due_date"])
        if due_date < payable_date:
            raise ValueError("payable due date precedes payable date")
        amount = _positive_money(payload["amount"], "payable amount")
        vendor = str(payload["vendor"]).strip()
        description = str(payload["description"]).strip()
        if not vendor or not description:
            raise ValueError("payable vendor and description are required")
        identity = {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "vendor": vendor,
            "payable_date": payable_date.isoformat(),
            "due_date": due_date.isoformat(),
            "description": description,
            "amount": amount,
        }
        return VendorPayable(
            payable_id=f"payable-{_digest(identity)[:20]}",
            paid_amount=0.0,
            outstanding_balance=amount,
            status="open",
            payment_records=(),
            **identity,
        )

    def apply_invoice_payment(
        self,
        invoice: Invoice,
        payload: dict[str, object],
    ) -> Invoice:
        payment = self._payment(
            invoice.tenant_id,
            "invoice",
            invoice.invoice_id,
            invoice.outstanding_balance,
            payload,
        )
        paid = _money(invoice.paid_amount + payment.amount)
        outstanding = _money(invoice.total - paid)
        return replace(
            invoice,
            paid_amount=paid,
            outstanding_balance=outstanding,
            status="paid" if outstanding == 0 else "partial",
            payment_records=(*invoice.payment_records, payment),
        )

    def apply_payable_payment(
        self,
        payable: VendorPayable,
        payload: dict[str, object],
    ) -> VendorPayable:
        payment = self._payment(
            payable.tenant_id,
            "payable",
            payable.payable_id,
            payable.outstanding_balance,
            payload,
        )
        paid = _money(payable.paid_amount + payment.amount)
        outstanding = _money(payable.amount - paid)
        return replace(
            payable,
            paid_amount=paid,
            outstanding_balance=outstanding,
            status="paid" if outstanding == 0 else "partial",
            payment_records=(*payable.payment_records, payment),
        )

    def _payment(
        self,
        tenant_id: str,
        target_type: str,
        target_id: str,
        outstanding: float,
        payload: dict[str, object],
    ) -> PaymentRecord:
        if outstanding <= 0:
            raise ValueError(f"{target_type} is already paid")
        amount = _positive_money(payload["amount"], "payment amount")
        if amount > outstanding:
            raise ValueError("payment exceeds outstanding balance")
        identity = {
            "tenant_id": tenant_id,
            "target_type": target_type,
            "target_id": target_id,
            "payment_date": _date(payload["payment_date"]).isoformat(),
            "amount": amount,
            "method": str(payload.get("method", "other")),
            "reference": str(payload.get("reference", "")),
        }
        return PaymentRecord(
            payment_id=f"payment-{_digest(identity)[:20]}",
            **identity,
        )


def _date(value: object) -> date:
    return date.fromisoformat(str(value))


def _positive_money(value: object, label: str) -> float:
    result = _money(float(value))
    if result <= 0:
        raise ValueError(f"{label} must be positive")
    return result


def _non_negative_money(value: object, label: str) -> float:
    result = _money(float(value))
    if result < 0:
        raise ValueError(f"{label} cannot be negative")
    return result


def _money(value: float) -> float:
    return round(float(value), 2)


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
