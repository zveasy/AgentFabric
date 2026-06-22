from reno_estimator.models import ProjectIntake


def test_domain_record_is_immutable() -> None:
    record = ProjectIntake(record_id="example")
    assert record.record_id == "example"
