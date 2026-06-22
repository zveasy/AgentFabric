from change_order_agent.models import ChangeOrder


def test_domain_record_is_immutable() -> None:
    record = ChangeOrder(record_id="example")
    assert record.record_id == "example"
