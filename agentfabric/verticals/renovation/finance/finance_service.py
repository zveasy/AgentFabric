"""Deterministic job-cost recording."""

from __future__ import annotations

from datetime import date
from hashlib import sha256
import json

from .models import (
    ActualLaborCost,
    ActualMaterialCost,
    JobCostRecord,
    OverheadAllocation,
    SubcontractorCost,
)


COST_CATEGORIES = {"material", "labor", "subcontractor", "fee", "tax", "overhead"}


class FinanceService:
    def record_cost(
        self,
        tenant_id: str,
        job_id: str,
        payload: dict[str, object],
    ) -> JobCostRecord:
        category = str(payload["category"]).strip().lower()
        cost_date = date.fromisoformat(str(payload["cost_date"])).isoformat()
        description = str(payload["description"]).strip()
        source_reference = str(payload.get("source_reference", "")).strip()
        if category not in COST_CATEGORIES:
            raise ValueError("invalid renovation job cost category")
        if not description:
            raise ValueError("job cost description is required")

        material = None
        labor = None
        subcontractor = None
        overhead = None
        if category == "material":
            quantity = _positive(payload.get("quantity", 1), "material quantity")
            unit_cost = _non_negative(payload["unit_cost"], "material unit cost")
            amount = _money(quantity * unit_cost)
            material = ActualMaterialCost(
                description=description,
                quantity=quantity,
                unit=str(payload.get("unit", "item")),
                unit_cost=_money(unit_cost),
                amount=amount,
            )
        elif category == "labor":
            hours = _positive(payload["hours"], "labor hours")
            hourly_rate = _non_negative(payload["hourly_rate"], "labor hourly rate")
            amount = _money(hours * hourly_rate)
            labor = ActualLaborCost(
                description=description,
                hours=hours,
                hourly_rate=_money(hourly_rate),
                amount=amount,
            )
        elif category == "subcontractor":
            amount = _non_negative_money(payload["amount"], "subcontractor amount")
            vendor = str(payload["vendor"]).strip()
            if not vendor:
                raise ValueError("subcontractor vendor is required")
            subcontractor = SubcontractorCost(
                vendor=vendor,
                description=description,
                amount=amount,
            )
        elif category == "overhead":
            amount = _non_negative_money(payload["amount"], "overhead amount")
            overhead = OverheadAllocation(
                description=description,
                allocation_method=str(payload.get("allocation_method", "direct")),
                amount=amount,
            )
        else:
            amount = _non_negative_money(payload["amount"], f"{category} amount")

        identity = {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "cost_date": cost_date,
            "category": category,
            "description": description,
            "amount": amount,
            "source_reference": source_reference,
            "material": material.as_dict() if material else None,
            "labor": labor.as_dict() if labor else None,
            "subcontractor": subcontractor.as_dict() if subcontractor else None,
            "overhead": overhead.as_dict() if overhead else None,
        }
        return JobCostRecord(
            cost_record_id=f"cost-{_digest(identity)[:20]}",
            material=material,
            labor=labor,
            subcontractor=subcontractor,
            overhead=overhead,
            **{key: value for key, value in identity.items() if key not in {
                "material", "labor", "subcontractor", "overhead"
            }},
        )


def _positive(value: object, label: str) -> float:
    result = float(value)
    if result <= 0:
        raise ValueError(f"{label} must be positive")
    return result


def _non_negative(value: object, label: str) -> float:
    result = float(value)
    if result < 0:
        raise ValueError(f"{label} cannot be negative")
    return result


def _non_negative_money(value: object, label: str) -> float:
    return _money(_non_negative(value, label))


def _money(value: float) -> float:
    return round(float(value), 2)


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
