from contractor_command_center.models import ContractorProfile


def test_domain_record_is_immutable() -> None:
    record = ContractorProfile(record_id="example")
    assert record.record_id == "example"
