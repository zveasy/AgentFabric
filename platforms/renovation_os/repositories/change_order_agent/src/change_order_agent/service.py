"""Deterministic change-order workflow."""

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
