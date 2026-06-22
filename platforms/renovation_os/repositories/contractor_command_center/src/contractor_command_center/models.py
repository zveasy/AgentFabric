"""Typed contractor operations models."""

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
