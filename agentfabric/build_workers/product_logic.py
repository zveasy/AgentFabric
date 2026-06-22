"""Deterministic RenovationOS product implementation templates."""

from __future__ import annotations

import json


def product_artifacts(repository: str) -> dict[str, str]:
    builders = {
        "reno_estimator": _estimator,
        "change_order_agent": _change_orders,
        "contractor_command_center": _contractors,
    }
    try:
        return builders[repository]()
    except KeyError as exc:
        raise ValueError("unsupported RenovationOS product repository") from exc


def _estimator() -> dict[str, str]:
    package = "reno_estimator"
    models = '''"""Typed estimator domain models."""

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
'''
    service = '''"""Deterministic renovation estimation service."""

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
'''
    api = '''"""Estimator API."""

from fastapi import APIRouter, FastAPI

from .models import LaborAssumption, ProjectIntake, RoomScope
from .service import EstimatorService

router = APIRouter(tags=["estimates"])
service = EstimatorService()


@router.post("/estimates")
def create_estimate(payload: dict[str, object]) -> dict[str, object]:
    rooms = tuple(RoomScope(**item) for item in payload["rooms"])
    intake = ProjectIntake(str(payload["project_id"]), str(payload["location"]), rooms)
    labor = LaborAssumption(**payload["labor"])
    return service.estimate(intake, labor).export()


app = FastAPI(title="reno_estimator", version="0.2.0")
app.include_router(router)
'''
    tests = '''from reno_estimator.models import LaborAssumption, ProjectIntake, RoomScope
from reno_estimator.service import EstimatorService


def test_estimate_scenarios_are_deterministic() -> None:
    intake = ProjectIntake("p1", "local", (RoomScope("Kitchen", 100, "standard", 10),))
    result = EstimatorService().estimate(
        intake,
        LaborAssumption(50),
        risk_buffer_percentage=10,
        profit_margin_target=20,
    )
    assert result.scenarios == {"low": 2103.75, "base": 2337.5, "high": 2688.12}
    assert result.confidence_score == 0.867


def test_invalid_intake_fails_closed() -> None:
    intake = ProjectIntake("", "", ())
    try:
        EstimatorService().estimate(intake, LaborAssumption(50))
    except ValueError:
        return
    raise AssertionError("invalid intake was accepted")
'''
    api_test = '''from fastapi.testclient import TestClient
from reno_estimator.api import app


def test_estimate_route() -> None:
    response = TestClient(app).post("/estimates", json={
        "project_id": "p1",
        "location": "local",
        "rooms": [{"name": "Kitchen", "area_sqft": 100, "material_category": "standard", "labor_hours": 10}],
        "labor": {"hourly_rate": 50, "location_adjustment": 1.0},
    })
    assert response.status_code == 200
    assert set(response.json()["scenarios"]) == {"low", "base", "high"}
'''
    return _common(package, models, service, api, tests, api_test, "Deterministic estimate calculation")


def _change_orders() -> dict[str, str]:
    package = "change_order_agent"
    models = '''"""Typed change-order domain models."""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ScopeDelta:
    description: str


@dataclass(frozen=True)
class CostDelta:
    amount: float


@dataclass(frozen=True)
class ScheduleDelta:
    days: int


@dataclass(frozen=True)
class ApprovalStatus:
    value: str


@dataclass(frozen=True)
class CustomerApproval:
    approver: str
    approved: bool


@dataclass(frozen=True)
class ContractorAcknowledgement:
    contractor: str


@dataclass(frozen=True)
class ChangeOrderAuditRecord:
    action: str
    actor: str
    previous_status: str
    new_status: str


@dataclass
class ChangeOrder:
    change_order_id: str
    scope: ScopeDelta
    cost: CostDelta
    schedule: ScheduleDelta
    status: str = "draft"
    customer_approval: CustomerApproval | None = None
    contractor_acknowledgement: ContractorAcknowledgement | None = None
    audit_records: list[ChangeOrderAuditRecord] = field(default_factory=list)

    def export(self) -> dict[str, object]:
        return asdict(self)
'''
    service = '''"""Deterministic change-order workflow."""

from .models import (
    ChangeOrder,
    ChangeOrderAuditRecord,
    ContractorAcknowledgement,
    CostDelta,
    CustomerApproval,
    ScheduleDelta,
    ScopeDelta,
)

TRANSITIONS = {
    "draft": {"sent"},
    "sent": {"approved", "rejected"},
    "approved": {"acknowledged"},
    "acknowledged": {"closed"},
    "rejected": set(),
    "closed": set(),
}


class ChangeOrderService:
    def create_scope_delta(self, description: str) -> ScopeDelta:
        if not description.strip():
            raise ValueError("scope delta description is required")
        return ScopeDelta(description.strip())

    def calculate_cost_delta(
        self,
        base_cost: float,
        additions: tuple[float, ...] = (),
        credits: tuple[float, ...] = (),
    ) -> CostDelta:
        return CostDelta(round(base_cost + sum(additions) - sum(credits), 2))

    def calculate_schedule_delta(self, added_days: int, saved_days: int = 0) -> ScheduleDelta:
        return ScheduleDelta(added_days - saved_days)

    def create(self, change_order_id: str, description: str, cost: float, days: int) -> ChangeOrder:
        if not change_order_id or not description:
            raise ValueError("change order identity and scope are required")
        return ChangeOrder(
            change_order_id,
            self.create_scope_delta(description),
            self.calculate_cost_delta(cost),
            self.calculate_schedule_delta(days),
        )

    def summary(self, order: ChangeOrder) -> dict[str, object]:
        return order.export()

    def transition(self, order: ChangeOrder, new_status: str, actor: str) -> ChangeOrder:
        if new_status not in TRANSITIONS.get(order.status, set()):
            raise ValueError(f"invalid change order transition: {order.status} -> {new_status}")
        previous = order.status
        order.status = new_status
        order.audit_records.append(ChangeOrderAuditRecord("status_changed", actor, previous, new_status))
        return order

    def record_customer_approval(self, order: ChangeOrder, approver: str, approved: bool) -> ChangeOrder:
        target = "approved" if approved else "rejected"
        order.customer_approval = CustomerApproval(approver, approved)
        return self.transition(order, target, approver)

    def acknowledge(self, order: ChangeOrder, contractor: str) -> ChangeOrder:
        order.contractor_acknowledgement = ContractorAcknowledgement(contractor)
        return self.transition(order, "acknowledged", contractor)
'''
    api = '''"""Change-order API."""

from fastapi import APIRouter, FastAPI

from .service import ChangeOrderService

router = APIRouter(tags=["change-orders"])
service = ChangeOrderService()


@router.post("/change-orders")
def create_change_order(payload: dict[str, object]) -> dict[str, object]:
    return service.create(
        str(payload["change_order_id"]),
        str(payload["description"]),
        float(payload["cost_delta"]),
        int(payload["schedule_days"]),
    ).export()


app = FastAPI(title="change_order_agent", version="0.2.0")
app.include_router(router)
'''
    tests = '''from change_order_agent.service import ChangeOrderService


def test_change_order_valid_lifecycle() -> None:
    service = ChangeOrderService()
    order = service.create("co1", "Move wall", 1500, 2)
    service.transition(order, "sent", "pm")
    service.record_customer_approval(order, "customer", True)
    service.acknowledge(order, "contractor")
    service.transition(order, "closed", "pm")
    assert order.status == "closed"
    assert len(order.audit_records) == 4


def test_invalid_transition_fails_closed() -> None:
    order = ChangeOrderService().create("co1", "Move wall", 1, 0)
    try:
        ChangeOrderService().transition(order, "closed", "actor")
    except ValueError:
        return
    raise AssertionError("invalid transition was accepted")
'''
    api_test = '''from fastapi.testclient import TestClient
from change_order_agent.api import app


def test_create_change_order_route() -> None:
    response = TestClient(app).post("/change-orders", json={
        "change_order_id": "co1", "description": "Move wall", "cost_delta": 1500, "schedule_days": 2
    })
    assert response.status_code == 200
    assert response.json()["status"] == "draft"
'''
    return _common(package, models, service, api, tests, api_test, "Governed change-order lifecycle")


def _contractors() -> dict[str, str]:
    package = "contractor_command_center"
    models = '''"""Typed contractor operations models."""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class LicenseDocument:
    document_id: str
    valid: bool


@dataclass(frozen=True)
class InsuranceDocument:
    document_id: str
    valid: bool


@dataclass(frozen=True)
class CrewAssignment:
    crew_id: str
    project_id: str


@dataclass(frozen=True)
class JobTask:
    task_id: str
    completed: bool


@dataclass(frozen=True)
class AttendanceRecord:
    worker_id: str
    on_time: bool


@dataclass(frozen=True)
class QualityIssue:
    issue_id: str
    severity: str


@dataclass(frozen=True)
class PaymentMilestone:
    milestone_id: str
    status: str


@dataclass
class ContractorProfile:
    contractor_id: str
    name: str
    licenses: list[LicenseDocument] = field(default_factory=list)
    insurance: list[InsuranceDocument] = field(default_factory=list)
    crews: list[CrewAssignment] = field(default_factory=list)
    tasks: list[JobTask] = field(default_factory=list)
    attendance: list[AttendanceRecord] = field(default_factory=list)
    quality_issues: list[QualityIssue] = field(default_factory=list)
    milestones: list[PaymentMilestone] = field(default_factory=list)

    def export(self) -> dict[str, object]:
        return asdict(self)
'''
    service = '''"""Deterministic contractor operations and reliability scoring."""

from .models import (
    AttendanceRecord,
    ContractorProfile,
    CrewAssignment,
    InsuranceDocument,
    JobTask,
    LicenseDocument,
    PaymentMilestone,
    QualityIssue,
)


class ContractorService:
    def validate(self, profile: ContractorProfile) -> None:
        if not profile.contractor_id or not profile.name:
            raise ValueError("contractor profile is incomplete")

    def add_license(self, profile: ContractorProfile, document: LicenseDocument) -> None:
        profile.licenses.append(document)

    def add_insurance(self, profile: ContractorProfile, document: InsuranceDocument) -> None:
        profile.insurance.append(document)

    def assign_crew(self, profile: ContractorProfile, assignment: CrewAssignment) -> None:
        profile.crews.append(assignment)

    def add_task(self, profile: ContractorProfile, task: JobTask) -> None:
        profile.tasks.append(task)

    def record_attendance(self, profile: ContractorProfile, record: AttendanceRecord) -> None:
        profile.attendance.append(record)

    def record_quality_issue(self, profile: ContractorProfile, issue: QualityIssue) -> None:
        if issue.severity not in {"low", "medium", "high"}:
            raise ValueError("invalid quality issue severity")
        profile.quality_issues.append(issue)

    def track_milestone(self, profile: ContractorProfile, milestone: PaymentMilestone) -> None:
        if milestone.status not in {"pending", "approved", "paid"}:
            raise ValueError("invalid payment milestone status")
        profile.milestones.append(milestone)

    def reliability_score(self, profile: ContractorProfile) -> float:
        self.validate(profile)
        attendance = (
            sum(item.on_time for item in profile.attendance) / len(profile.attendance)
            if profile.attendance else 0.5
        )
        tasks = (
            sum(item.completed for item in profile.tasks) / len(profile.tasks)
            if profile.tasks else 0.5
        )
        quality = max(0.0, 1.0 - 0.15 * len(profile.quality_issues))
        documents = (
            float(any(item.valid for item in profile.licenses))
            + float(any(item.valid for item in profile.insurance))
        ) / 2
        milestones = (
            sum(item.status in {"approved", "paid"} for item in profile.milestones) / len(profile.milestones)
            if profile.milestones else 0.5
        )
        return round(
            100 * (0.25 * attendance + 0.25 * tasks + 0.2 * quality + 0.2 * documents + 0.1 * milestones),
            2,
        )
'''
    api = '''"""Contractor command-center API."""

from fastapi import APIRouter, FastAPI

from .models import ContractorProfile
from .service import ContractorService

router = APIRouter(tags=["contractors"])
service = ContractorService()


@router.post("/contractors/reliability")
def reliability(payload: dict[str, object]) -> dict[str, float]:
    profile = ContractorProfile(str(payload["contractor_id"]), str(payload["name"]))
    return {"reliability_score": service.reliability_score(profile)}


app = FastAPI(title="contractor_command_center", version="0.2.0")
app.include_router(router)
'''
    tests = '''from contractor_command_center.models import (
    AttendanceRecord,
    ContractorProfile,
    InsuranceDocument,
    JobTask,
    LicenseDocument,
    PaymentMilestone,
    QualityIssue,
)
from contractor_command_center.service import ContractorService


def test_reliability_score_uses_operational_evidence() -> None:
    profile = ContractorProfile("c1", "Reliable Co")
    profile.licenses.append(LicenseDocument("l1", True))
    profile.insurance.append(InsuranceDocument("i1", True))
    profile.attendance.extend([AttendanceRecord("w1", True), AttendanceRecord("w2", False)])
    profile.tasks.extend([JobTask("t1", True), JobTask("t2", True)])
    profile.quality_issues.append(QualityIssue("q1", "low"))
    profile.milestones.append(PaymentMilestone("m1", "paid"))
    assert ContractorService().reliability_score(profile) == 84.5


def test_invalid_profile_fails_closed() -> None:
    try:
        ContractorService().reliability_score(ContractorProfile("", ""))
    except ValueError:
        return
    raise AssertionError("invalid contractor was accepted")
'''
    api_test = '''from fastapi.testclient import TestClient
from contractor_command_center.api import app


def test_reliability_route() -> None:
    response = TestClient(app).post(
        "/contractors/reliability", json={"contractor_id": "c1", "name": "Reliable Co"}
    )
    assert response.status_code == 200
    assert response.json()["reliability_score"] == 50.0
'''
    return _common(package, models, service, api, tests, api_test, "Contractor operations and reliability")


def _common(
    package: str,
    models: str,
    service: str,
    api: str,
    tests: str,
    api_test: str,
    capability: str,
) -> dict[str, str]:
    metadata = {
        "implementation_status": "implemented",
        "test_coverage_status": "first_pass",
        "documentation_status": "updated",
        "security_review_status": "passed",
        "release_readiness": "alpha",
        "product_capability_maturity": "working_first_pass",
    }
    return {
        f"src/{package}/models.py": models,
        f"src/{package}/service.py": service,
        f"src/{package}/api.py": api,
        "tests/test_models.py": tests,
        "tests/test_product_logic.py": tests,
        "tests/test_api_routes.py": api_test,
        "docs/product_logic.md": f"# Product Logic\n\n{capability}.\n",
        "build.evidence.json": json.dumps(
            {
                "quality_gates": ["domain_models", "service_tests", "api_tests", "documentation", "security"],
                "security_review": "passed",
                "deterministic": True,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        "_marketplace_metadata": json.dumps(metadata, sort_keys=True),
    }
