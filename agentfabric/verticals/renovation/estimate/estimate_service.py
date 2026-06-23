"""Deterministic estimate construction."""

from __future__ import annotations

from hashlib import sha256
import json

from agentfabric.verticals.renovation.models import Estimate, Room

from .cost_calculator import CostCalculator
from .labor_estimator import LaborEstimator
from .material_estimator import MaterialEstimator
from .scope_parser import ScopeParser


class EstimateService:
    def __init__(self) -> None:
        self.scope_parser = ScopeParser()
        self.materials = MaterialEstimator()
        self.labor = LaborEstimator()
        self.costs = CostCalculator()

    def create(self, tenant_id: str, payload: dict[str, object]) -> Estimate:
        rooms = tuple(Room(**item) for item in payload.get("rooms", ()))
        items = self.scope_parser.parse(
            str(payload["scope_description"]),
            rooms,
            {str(key): float(value) for key, value in dict(payload.get("quantities", {})).items()},
            str(payload.get("notes", "")),
        )
        material_lines = self.materials.estimate(
            items,
            {str(key): float(value) for key, value in dict(payload.get("material_rates", {})).items()},
        )
        labor_lines = self.labor.estimate(
            items,
            float(payload.get("labor_rate", 65.0)),
            {str(key): float(value) for key, value in dict(payload.get("labor_hours", {})).items()},
        )
        material_total = round(sum(item.total for item in material_lines), 2)
        labor_total = round(sum(item.total for item in labor_lines), 2)
        totals = self.costs.calculate(
            material_total,
            labor_total,
            float(payload.get("contingency_percentage", 10.0)),
            float(payload.get("tax_percentage", 6.0)),
        )
        canonical_input = {
            "tenant_id": tenant_id,
            "project_id": str(payload["project_id"]),
            "scope_description": str(payload["scope_description"]),
            "rooms": [room.as_dict() for room in rooms],
            "quantities": dict(sorted(dict(payload.get("quantities", {})).items())),
            "notes": str(payload.get("notes", "")),
            "material_rates": dict(sorted(dict(payload.get("material_rates", {})).items())),
            "labor_rate": float(payload.get("labor_rate", 65.0)),
            "labor_hours": dict(sorted(dict(payload.get("labor_hours", {})).items())),
            "contingency_percentage": float(payload.get("contingency_percentage", 10.0)),
            "tax_percentage": float(payload.get("tax_percentage", 6.0)),
        }
        estimate_id = f"estimate-{_digest(canonical_input)[:20]}"
        return Estimate(
            estimate_id=estimate_id,
            tenant_id=tenant_id,
            project_id=str(payload["project_id"]),
            scope_description=str(payload["scope_description"]).strip(),
            scope_items=items,
            material_lines=material_lines,
            labor_lines=labor_lines,
            material_total=material_total,
            labor_total=labor_total,
            subtotal=totals["subtotal"],
            contingency_percentage=float(payload.get("contingency_percentage", 10.0)),
            contingency=totals["contingency"],
            taxable_amount=totals["taxable_amount"],
            tax_percentage=float(payload.get("tax_percentage", 6.0)),
            tax=totals["tax"],
            total=totals["total"],
            notes=str(payload.get("notes", "")).strip(),
        )


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
