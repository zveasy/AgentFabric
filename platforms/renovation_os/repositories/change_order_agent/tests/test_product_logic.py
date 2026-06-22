from change_order_agent.service import ChangeOrderService


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
