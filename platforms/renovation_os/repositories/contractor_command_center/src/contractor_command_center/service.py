"""Deterministic contractor operations and reliability scoring."""

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
