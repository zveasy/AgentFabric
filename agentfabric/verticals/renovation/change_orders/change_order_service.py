"""Deterministic change-order pricing, documents, and decisions."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json

from agentfabric.verticals.renovation.estimate.cost_calculator import CostCalculator
from agentfabric.verticals.renovation.estimate.labor_estimator import LaborEstimator
from agentfabric.verticals.renovation.estimate.material_estimator import MaterialEstimator
from agentfabric.verticals.renovation.models import Estimate, ScopeItem
from agentfabric.verticals.renovation.templates import load_template

from .models import ChangeOrder, ChangeOrderApproval, ChangeOrderLine


CHANGE_ORDER_STATUSES = {"draft", "sent", "approved", "rejected", "cancelled"}
SOURCE_TYPES = {"customer_request", "field_note", "scope_change"}


class ChangeOrderService:
    def __init__(self) -> None:
        self.materials = MaterialEstimator()
        self.labor = LaborEstimator()
        self.costs = CostCalculator()

    def create(
        self,
        tenant_id: str,
        job_id: str,
        proposal_id: str,
        estimate: Estimate,
        estimate_input: dict[str, object],
        payload: dict[str, object],
    ) -> ChangeOrder:
        source_type = str(payload.get("source_type", "scope_change"))
        status = str(payload.get("status", "sent"))
        if source_type not in SOURCE_TYPES:
            raise ValueError("invalid change order source type")
        if status not in {"draft", "sent"}:
            raise ValueError("new change orders must be draft or sent")
        raw_lines = list(payload.get("lines", ()))
        if not raw_lines:
            raise ValueError("change order lines are required")
        scope_items = tuple(
            ScopeItem(
                description=str(item["description"]),
                category=str(item["category"]),
                quantity=float(item["quantity"]),
                unit=str(item.get("unit", "item")),
                room=str(item.get("room", "")),
                notes=str(item.get("notes", "")),
            )
            for item in raw_lines
        )
        material_lines = self.materials.estimate(
            scope_items,
            {str(key): float(value) for key, value in dict(estimate_input.get("material_rates", {})).items()},
        )
        labor_lines = self.labor.estimate(
            scope_items,
            float(estimate_input.get("labor_rate", 65.0)),
            {str(key): float(value) for key, value in dict(estimate_input.get("labor_hours", {})).items()},
        )
        lines = tuple(
            ChangeOrderLine(
                description=scope.description,
                category=scope.category,
                quantity=scope.quantity,
                unit=scope.unit,
                material_cost=material.total,
                labor_hours=labor.hours,
                labor_cost=labor.total,
                total=round(material.total + labor.total, 2),
            )
            for scope, material, labor in zip(scope_items, material_lines, labor_lines)
        )
        material_total = round(sum(item.material_cost for item in lines), 2)
        labor_total = round(sum(item.labor_cost for item in lines), 2)
        contingency_percentage = float(
            payload.get("contingency_percentage", estimate.contingency_percentage)
        )
        tax_percentage = float(payload.get("tax_percentage", estimate.tax_percentage))
        totals = self.costs.calculate(
            material_total,
            labor_total,
            contingency_percentage,
            tax_percentage,
        )
        template = load_template(str(payload.get("template_id", "change_order_standard")))
        identity = {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "proposal_id": proposal_id,
            "source_type": source_type,
            "source_reference": str(payload["source_reference"]),
            "title": str(payload["title"]),
            "description": str(payload.get("description", "")),
            "lines": [item.as_dict() for item in lines],
            "schedule_delta_days": int(payload.get("schedule_delta_days", 0)),
            "template_id": template["template_id"],
            "template_version": template["version"],
        }
        change_order_id = f"change-{_digest(identity)[:20]}"
        order = ChangeOrder(
            change_order_id=change_order_id,
            tenant_id=tenant_id,
            job_id=job_id,
            proposal_id=proposal_id,
            source_type=source_type,
            source_reference=str(payload["source_reference"]),
            title=str(payload["title"]),
            description=str(payload.get("description", "")),
            status=status,
            lines=lines,
            material_total=material_total,
            labor_total=labor_total,
            subtotal=totals["subtotal"],
            contingency_percentage=contingency_percentage,
            contingency=totals["contingency"],
            tax_percentage=tax_percentage,
            tax=totals["tax"],
            total_adjustment=totals["total"],
            schedule_delta_days=int(payload.get("schedule_delta_days", 0)),
            template_id=str(template["template_id"]),
            template_version=str(template["version"]),
            approval_history=(),
            rendered_text="",
        )
        return replace(order, rendered_text=self.render(order, tuple(str(item) for item in template["clauses"])))

    def decide(
        self,
        order: ChangeOrder,
        decision: str,
        decision_date: str,
        decided_by: str,
        reason: str = "",
    ) -> ChangeOrder:
        if order.status != "sent":
            raise ValueError("only sent change orders may be approved or rejected")
        if decision not in {"approved", "rejected"}:
            raise ValueError("change order decision must be approved or rejected")
        identity = {
            "change_order_id": order.change_order_id,
            "decision": decision,
            "decision_date": decision_date,
            "decided_by": decided_by,
            "reason": reason,
        }
        approval = ChangeOrderApproval(
            approval_id=f"approval-{_digest(identity)[:20]}",
            change_order_id=order.change_order_id,
            decision=decision,
            decision_date=decision_date,
            decided_by=decided_by,
            reason=reason,
        )
        updated = replace(
            order,
            status=decision,
            approval_history=(*order.approval_history, approval),
        )
        template = load_template(order.template_id)
        return replace(
            updated,
            rendered_text=self.render(updated, tuple(str(item) for item in template["clauses"])),
        )

    def render(self, order: ChangeOrder, clauses: tuple[str, ...]) -> str:
        lines = "\n".join(
            f"- {item.description}: {item.quantity:g} {item.unit}, ${item.total:,.2f}"
            for item in order.lines
        )
        approvals = "\n".join(
            f"- {item.decision} by {item.decided_by} on {item.decision_date}: {item.reason}"
            for item in order.approval_history
        ) or "- Pending"
        terms = "\n".join(f"- {item}" for item in clauses)
        return (
            f"Change Order: {order.title}\n"
            f"Status: {order.status}\n"
            f"Source: {order.source_type} ({order.source_reference})\n\n"
            f"Scope Changes\n{lines}\n\n"
            f"Material Adjustment: ${order.material_total:,.2f}\n"
            f"Labor Adjustment: ${order.labor_total:,.2f}\n"
            f"Contingency: ${order.contingency:,.2f}\n"
            f"Tax: ${order.tax:,.2f}\n"
            f"Total Adjustment: ${order.total_adjustment:,.2f}\n"
            f"Schedule Adjustment: {order.schedule_delta_days} days\n\n"
            f"Approval History\n{approvals}\n\n"
            f"Terms\n{terms}\n"
        )


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
