"""Typed estimator domain models."""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ProjectIntake:
    project_id: str
    location: str
    rooms: tuple["RoomScope", ...]


@dataclass(frozen=True)
class RoomScope:
    name: str
    area_sqft: float
    material_category: str
    labor_hours: float


@dataclass(frozen=True)
class MaterialSelection:
    category: str
    unit_cost: float


@dataclass(frozen=True)
class LaborAssumption:
    hourly_rate: float
    location_adjustment: float = 1.0


@dataclass(frozen=True)
class EstimateLineItem:
    room: str
    material_cost: float
    labor_cost: float


@dataclass(frozen=True)
class MarginScenario:
    name: str
    multiplier: float


@dataclass(frozen=True)
class RiskAdjustment:
    risk_buffer_percentage: float


@dataclass(frozen=True)
class EstimateResult:
    project_id: str
    line_items: tuple[EstimateLineItem, ...]
    scenarios: dict[str, float]
    confidence_score: float
    assumptions: dict[str, float] = field(default_factory=dict)

    def export(self) -> dict[str, object]:
        return asdict(self)
