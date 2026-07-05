"""Deterministic renovation opportunity and follow-up workflows."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from hashlib import sha256
import json

from .models import AppointmentRequest, FollowUpTask, Opportunity, SiteVisit


OPPORTUNITY_STAGES = (
    "qualification",
    "appointment",
    "estimating",
    "proposal",
    "negotiation",
    "won",
    "lost",
)
APPOINTMENT_STATUSES = {"requested", "scheduled", "completed", "cancelled"}


class CrmService:
    def opportunity(
        self,
        tenant_id: str,
        payload: dict[str, object],
    ) -> Opportunity:
        expected_value = _non_negative(payload["expected_value"], "expected value")
        probability = float(payload["probability"])
        stage = str(payload.get("stage", "qualification"))
        expected_close_date = date.fromisoformat(
            str(payload["expected_close_date"])
        ).isoformat()
        if probability < 0 or probability > 100:
            raise ValueError("opportunity probability must be between 0 and 100")
        if stage not in OPPORTUNITY_STAGES:
            raise ValueError("invalid opportunity stage")
        identity = {
            "tenant_id": tenant_id,
            "lead_id": str(payload.get("lead_id", "")),
            "customer_id": str(payload.get("customer_id", "")),
            "project_type": str(payload["project_type"]).strip(),
            "expected_value": round(expected_value, 2),
            "probability": round(probability, 2),
            "stage": stage,
            "expected_close_date": expected_close_date,
        }
        if not identity["project_type"] or not (
            identity["lead_id"] or identity["customer_id"]
        ):
            raise ValueError("opportunity requires project type and lead or customer")
        return Opportunity(
            opportunity_id=f"opportunity-{_digest(identity)[:20]}",
            weighted_value=round(expected_value * probability / 100, 2),
            **identity,
        )

    def update_stage(self, opportunity: Opportunity, stage: str) -> Opportunity:
        if stage not in OPPORTUNITY_STAGES:
            raise ValueError("invalid opportunity stage")
        current = OPPORTUNITY_STAGES.index(opportunity.stage)
        target = OPPORTUNITY_STAGES.index(stage)
        if opportunity.stage in {"won", "lost"} or target < current:
            raise ValueError("invalid opportunity stage transition")
        return replace(opportunity, stage=stage)

    def follow_up(self, tenant_id: str, payload: dict[str, object]) -> FollowUpTask:
        due_date = date.fromisoformat(str(payload["due_date"]))
        reminder_days = int(payload.get("reminder_days_before", 1))
        if reminder_days < 0:
            raise ValueError("reminder days cannot be negative")
        identity = {
            "tenant_id": tenant_id,
            "lead_id": str(payload.get("lead_id", "")),
            "opportunity_id": str(payload.get("opportunity_id", "")),
            "task_type": str(payload.get("task_type", "contact")),
            "due_date": due_date.isoformat(),
            "description": str(payload["description"]).strip(),
        }
        if not identity["description"] or not (
            identity["lead_id"] or identity["opportunity_id"]
        ):
            raise ValueError("follow-up requires a target and description")
        return FollowUpTask(
            follow_up_id=f"followup-{_digest(identity)[:20]}",
            status="pending",
            reminder_date=(due_date - timedelta(days=reminder_days)).isoformat(),
            **identity,
        )

    def appointment(
        self,
        tenant_id: str,
        payload: dict[str, object],
    ) -> AppointmentRequest:
        requested_date = date.fromisoformat(str(payload["requested_date"])).isoformat()
        status = str(payload.get("status", "requested"))
        if status not in APPOINTMENT_STATUSES:
            raise ValueError("invalid appointment status")
        identity = {
            "tenant_id": tenant_id,
            "lead_id": str(payload.get("lead_id", "")),
            "customer_id": str(payload.get("customer_id", "")),
            "requested_date": requested_date,
            "requested_time": str(payload.get("requested_time", "")),
            "appointment_type": str(payload.get("appointment_type", "site_visit")),
            "property_address": str(payload["property_address"]).strip(),
            "status": status,
            "notes": str(payload.get("notes", "")),
        }
        if not (identity["lead_id"] or identity["customer_id"]):
            raise ValueError("appointment requires lead or customer")
        return AppointmentRequest(
            appointment_id=f"appointment-{_digest(identity)[:20]}",
            **identity,
        )

    def site_visit(
        self,
        tenant_id: str,
        appointment: AppointmentRequest,
        payload: dict[str, object],
    ) -> SiteVisit:
        identity = {
            "tenant_id": tenant_id,
            "appointment_id": appointment.appointment_id,
            "lead_id": appointment.lead_id,
            "customer_id": appointment.customer_id,
            "visit_date": date.fromisoformat(str(payload["visit_date"])).isoformat(),
            "visited_by": str(payload["visited_by"]).strip(),
            "summary": str(payload["summary"]).strip(),
            "next_step": str(payload.get("next_step", "")),
        }
        if not identity["visited_by"] or not identity["summary"]:
            raise ValueError("site visit requires visitor and summary")
        return SiteVisit(
            site_visit_id=f"site-visit-{_digest(identity)[:20]}",
            **identity,
        )


def _non_negative(value: object, label: str) -> float:
    result = float(value)
    if result < 0:
        raise ValueError(f"{label} cannot be negative")
    return result


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
