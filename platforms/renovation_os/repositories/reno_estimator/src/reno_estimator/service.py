"""Deterministic renovation estimation service."""

from .models import EstimateLineItem, EstimateResult, LaborAssumption, ProjectIntake

MATERIAL_MULTIPLIERS = {"economy": 0.85, "standard": 1.0, "premium": 1.35}
SCENARIO_MULTIPLIERS = {"low": 0.9, "base": 1.0, "high": 1.15}


class EstimatorService:
    def validate_intake(self, intake: ProjectIntake) -> None:
        if not intake.project_id or not intake.location or not intake.rooms:
            raise ValueError("project intake is incomplete")
        if any(room.area_sqft <= 0 or room.labor_hours < 0 for room in intake.rooms):
            raise ValueError("room scope values must be non-negative")
        if any(room.material_category not in MATERIAL_MULTIPLIERS for room in intake.rooms):
            raise ValueError("unsupported material category")

    def normalize_room(self, room):
        return type(room)(
            room.name.strip().lower(),
            round(room.area_sqft, 2),
            room.material_category.strip().lower(),
            round(room.labor_hours, 2),
        )

    def calculate_material_cost(self, room, base_material_rate: float) -> float:
        return round(
            room.area_sqft * base_material_rate * MATERIAL_MULTIPLIERS[room.material_category],
            2,
        )

    def calculate_labor_cost(self, room, labor: LaborAssumption) -> float:
        return round(room.labor_hours * labor.hourly_rate * labor.location_adjustment, 2)

    def apply_risk_adjustment(self, subtotal: float, percentage: float) -> float:
        return round(subtotal * (1 + percentage / 100), 2)

    def calculate_margin_scenarios(self, cost: float, target: float) -> dict[str, float]:
        sell_price = cost / (1 - target / 100)
        return {
            name: round(sell_price * multiplier, 2)
            for name, multiplier in SCENARIO_MULTIPLIERS.items()
        }

    def confidence_score(self, room_count: int, risk_buffer_percentage: float) -> float:
        completeness = min(1.0, room_count / 3)
        return round(0.7 + 0.2 * completeness + 0.1 * (risk_buffer_percentage > 0), 3)

    def export_result(self, result: EstimateResult) -> dict[str, object]:
        return result.export()

    def estimate(
        self,
        intake: ProjectIntake,
        labor: LaborAssumption,
        *,
        base_material_rate: float = 12.0,
        risk_buffer_percentage: float = 10.0,
        profit_margin_target: float = 20.0,
    ) -> EstimateResult:
        self.validate_intake(intake)
        if labor.hourly_rate <= 0 or labor.location_adjustment <= 0:
            raise ValueError("labor assumptions must be positive")
        if not 0 <= risk_buffer_percentage <= 100 or not 0 <= profit_margin_target < 100:
            raise ValueError("risk and margin percentages are invalid")
        items = []
        for raw_room in sorted(intake.rooms, key=lambda item: item.name):
            room = self.normalize_room(raw_room)
            material = self.calculate_material_cost(room, base_material_rate)
            labor_cost = self.calculate_labor_cost(room, labor)
            items.append(EstimateLineItem(room.name, material, labor_cost))
        subtotal = sum(item.material_cost + item.labor_cost for item in items)
        risk_adjusted = self.apply_risk_adjustment(subtotal, risk_buffer_percentage)
        scenarios = self.calculate_margin_scenarios(risk_adjusted, profit_margin_target)
        confidence = self.confidence_score(len(items), risk_buffer_percentage)
        return EstimateResult(
            project_id=intake.project_id,
            line_items=tuple(items),
            scenarios=scenarios,
            confidence_score=confidence,
            assumptions={
                "base_material_rate": base_material_rate,
                "location_adjustment": labor.location_adjustment,
                "risk_buffer_percentage": risk_buffer_percentage,
                "profit_margin_target": profit_margin_target,
            },
        )
