"""Deterministic material delivery tracking."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from hashlib import sha256
import json

from .models import MaterialDelivery


DELIVERY_STATUSES = {"planned", "ordered", "in_transit", "delivered", "delayed", "cancelled"}


class DeliveryService:
    def create(
        self,
        tenant_id: str,
        job_id: str,
        schedule_id: str,
        phase_id: str,
        payload: dict[str, object],
    ) -> MaterialDelivery:
        material = str(payload["material"]).strip()
        quantity = float(payload["quantity"])
        unit = str(payload["unit"]).strip()
        required = _date(str(payload["required_date"]))
        expected = _date(str(payload.get("expected_date", payload["required_date"])))
        actual = str(payload.get("actual_date", "")).strip()
        if actual:
            _date(actual)
        status = str(payload.get("status", "planned"))
        if not material or not unit or quantity <= 0:
            raise ValueError("delivery material, positive quantity, and unit are required")
        if status not in DELIVERY_STATUSES:
            raise ValueError("invalid material delivery status")
        identity = {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "schedule_id": schedule_id,
            "phase_id": phase_id,
            "material": material,
            "quantity": quantity,
            "unit": unit,
            "required_date": required.isoformat(),
            "supplier_reference": str(payload.get("supplier_reference", "")),
        }
        return MaterialDelivery(
            delivery_id=f"delivery-{_digest(identity)[:20]}",
            expected_date=expected.isoformat(),
            actual_date=actual,
            status=status,
            **identity,
        )

    def update(
        self,
        delivery: MaterialDelivery,
        payload: dict[str, object],
    ) -> MaterialDelivery:
        expected_date = str(payload.get("expected_date", delivery.expected_date))
        actual_date = str(payload.get("actual_date", delivery.actual_date))
        status = str(payload.get("status", delivery.status))
        _date(expected_date)
        if actual_date:
            _date(actual_date)
        if status not in DELIVERY_STATUSES:
            raise ValueError("invalid material delivery status")
        return replace(
            delivery,
            expected_date=expected_date,
            actual_date=actual_date,
            status=status,
        )


def delivery_effective_date(delivery: MaterialDelivery) -> date:
    return _date(delivery.actual_date or delivery.expected_date)


def _date(value: str) -> date:
    return date.fromisoformat(value)


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
