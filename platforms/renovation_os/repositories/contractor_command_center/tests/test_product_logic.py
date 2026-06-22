from contractor_command_center.models import (
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
