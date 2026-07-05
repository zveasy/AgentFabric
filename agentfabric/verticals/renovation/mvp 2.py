"""End-to-end RenovationOS MVP workflow helpers."""

from __future__ import annotations

from copy import deepcopy

from agentfabric.enterprise import TenantContext

from .service import RenovationFoundationService


DEFAULT_MVP_PAYLOAD: dict[str, object] = {
    "lead": {
        "name": "Morgan Homeowner",
        "email": "morgan@example.com",
        "phone": "555-0140",
        "property_address": "200 Oak Street",
        "project_type": "kitchen_remodel",
        "description": "Replace cabinets, counters, and flooring.",
        "created_date": "2026-08-01",
        "source": {
            "source_type": "website",
            "source_name": "renovationos-demo",
            "campaign": "mvp-demo",
        },
    },
    "estimate": {
        "project_id": "project-mvp-kitchen",
        "scope_description": "Cabinet replacement\nFlooring replacement",
        "rooms": [
            {
                "name": "Kitchen",
                "length_ft": 20,
                "width_ft": 15,
                "quantity": 1,
                "notes": "Main floor",
            }
        ],
        "quantities": {"cabinetry": 10, "flooring": 300},
        "labor_rate": 65,
        "contingency_percentage": 10,
        "tax_percentage": 6,
        "notes": "MVP deterministic estimate",
    },
    "proposal": {
        "project": {
            "project_id": "project-mvp-kitchen",
            "title": "Kitchen Remodel",
            "property_address": "200 Oak Street",
            "notes": "Occupied residence",
        },
        "template_id": "standard_proposal",
    },
    "job": {
        "accepted": True,
        "accepted_date": "2026-08-03",
        "acceptance_reference": "mvp-signed-proposal",
    },
    "schedule": {"start_date": "2026-08-10"},
    "daily_log": {
        "work_date": "2026-08-10",
        "summary": "Completed site protection and cabinet field verification.",
        "weather": "Clear",
        "crew_hours": 12,
        "completed_work": ["Site protection", "Cabinet measurement"],
        "next_steps": ["Begin demolition", "Confirm flooring delivery"],
    },
    "cost": {
        "cost_date": "2026-08-11",
        "category": "material",
        "description": "Cabinet package",
        "quantity": 10,
        "unit": "cabinet",
        "unit_cost": 900,
        "source_reference": "vendor-invoice-mvp",
    },
    "invoice": {
        "invoice_date": "2026-08-03",
        "due_date": "2026-08-17",
        "description": "Project deposit",
        "amount": 5000,
        "tax": 0,
    },
    "payment": {
        "payment_date": "2026-08-05",
        "amount": 1000,
        "method": "ach",
    },
    "message": {
        "channel": "portal",
        "message_date": "2026-08-10",
        "body": "Site protection is complete and the project is on schedule.",
    },
    "generated_date": "2026-08-10",
}


def run_mvp_workflow(
    service: RenovationFoundationService,
    ctx: TenantContext,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    """Run the shortest complete contractor workflow and return the generated artifacts."""

    data = _deep_merge(DEFAULT_MVP_PAYLOAD, payload or {})

    lead = service.create_lead(ctx, dict(data["lead"]))
    for status in ("contacted", "estimate_scheduled", "proposal_sent", "won"):
        lead = service.update_lead(ctx, lead.lead_id, {"status": status})
    customer = service.convert_lead(ctx, lead.lead_id, {})

    estimate = service.create_estimate(ctx, dict(data["estimate"]))
    proposal_payload = dict(data["proposal"])
    proposal_payload["estimate_id"] = estimate.estimate_id
    proposal_payload["customer"] = customer.as_dict()
    proposal = service.create_proposal(ctx, proposal_payload)

    job_payload = dict(data["job"])
    job_payload["proposal_id"] = proposal.proposal_id
    job = service.create_job(ctx, job_payload)

    schedule_payload = dict(data["schedule"])
    schedule_payload["job_id"] = job.job_id
    schedule = service.create_schedule(ctx, schedule_payload)

    service.add_daily_log(ctx, job.job_id, dict(data["daily_log"]))
    cost = service.record_job_cost(ctx, job.job_id, dict(data["cost"]))
    profitability = service.job_profitability(ctx, job.job_id)

    invoice_payload = dict(data["invoice"])
    invoice_payload["job_id"] = job.job_id
    invoice = service.create_invoice(ctx, invoice_payload)
    invoice = service.pay_invoice(ctx, invoice.invoice_id, dict(data["payment"]))

    message_payload = dict(data["message"])
    message_payload["customer_id"] = customer.customer_id
    message_payload["job_id"] = job.job_id
    message = service.record_customer_message(ctx, message_payload)

    generated_date = str(data["generated_date"])
    portal = service.customer_portal_view(ctx, customer.customer_id, generated_date)
    customer_status = service.customer_job_status(ctx, job.job_id, generated_date)
    owner_summary = service.owner_financial_summary(ctx, generated_date)

    return {
        "status": "complete",
        "tenant_id": ctx.tenant_id,
        "lead": lead.as_dict(),
        "customer": customer.as_dict(),
        "estimate": estimate.as_dict(),
        "proposal": proposal.as_dict(),
        "job": job.as_dict(),
        "schedule": schedule.as_dict(),
        "cost": cost.as_dict(),
        "profitability": profitability.as_dict(),
        "invoice": invoice.as_dict(),
        "message": message.as_dict(),
        "portal": portal.as_dict(),
        "customer_status": customer_status,
        "owner_summary": owner_summary,
    }


def _deep_merge(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = deepcopy(value)
    return merged
