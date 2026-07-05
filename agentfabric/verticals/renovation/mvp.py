"""Persisted end-to-end RenovationOS MVP workflow helpers."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Callable
from uuid import uuid4

from agentfabric.enterprise import TenantContext
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore

from .service import RenovationFoundationService

MVP_RUNS = "renovation_mvp_runs"
MVP_IDEMPOTENCY = "renovation_mvp_idempotency"

STEP_PENDING = "pending"
STEP_RUNNING = "running"
STEP_COMPLETED = "completed"
STEP_FAILED = "failed"
STEP_SKIPPED = "skipped"

RUN_CREATED = "renovation.mvp.run.created"
STEP_STARTED = "renovation.mvp.step.started"
STEP_COMPLETED_EVENT = "renovation.mvp.step.completed"
STEP_FAILED_EVENT = "renovation.mvp.step.failed"
RUN_COMPLETED = "renovation.mvp.run.completed"
RUN_FAILED = "renovation.mvp.run.failed"
RUN_REPLAYED = "renovation.mvp.run.replayed"
RUN_RESUMED = "renovation.mvp.run.resumed"
INVOICE_PAYMENT_GENERATED = "renovation.mvp.invoice_payment.generated"
PORTAL_STATUS_VIEWED = "renovation.mvp.portal_status.viewed"

WORKFLOW_STEPS = (
    "lead",
    "estimate",
    "proposal",
    "job",
    "schedule",
    "cost_profitability",
    "invoice_payment",
    "portal_status",
)

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


class RenovationMvpWorkflow:
    """Durable, idempotent coordinator for the local RenovationOS MVP path."""

    def __init__(
        self,
        service: RenovationFoundationService,
        persistence: PersistenceStore,
        event_store: EventStore,
    ) -> None:
        self.service = service
        self.persistence = persistence
        self.event_store = event_store

    def create_run(self, ctx: TenantContext, request: dict[str, object]) -> dict[str, object]:
        payload = _normalized_payload(request)
        idempotency_key = _idempotency_key(request)
        if idempotency_key:
            existing = self._get_idempotent(ctx, idempotency_key)
            if existing is not None:
                return existing

        run_id = str(request.get("run_id") or _stable_run_id(ctx, idempotency_key, payload))
        run = {
            "run_id": run_id,
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": ctx.principal_id,
            "idempotency_key": idempotency_key,
            "status": "running",
            "payload": payload,
            "steps": {
                step: {"status": STEP_PENDING, "output": {}, "error": ""}
                for step in WORKFLOW_STEPS
            },
            "entity_ids": {},
            "financial_summary": {},
            "portal": {},
            "customer_status": {},
            "error": "",
            "failed_step": "",
            "replay_count": 0,
            "resume_count": 0,
        }
        self._put(run)
        if idempotency_key:
            self.persistence.put(
                MVP_IDEMPOTENCY,
                self._idempotency_index_key(ctx, idempotency_key),
                {"tenant_id": ctx.tenant_id, "idempotency_key": idempotency_key, "run_id": run_id},
            )
        self._event(ctx, RUN_CREATED, run_id, {"idempotency_key": idempotency_key})
        return self._execute(ctx, run)

    def get_run(self, ctx: TenantContext, run_id: str) -> dict[str, object]:
        return self._tenant_run(ctx, run_id)

    def list_runs(self, ctx: TenantContext) -> dict[str, object]:
        items = [
            _public_run(item)
            for item in self.persistence.list_tenant(MVP_RUNS, ctx.tenant_id)
        ]
        return {"items": items, "total": len(items)}

    def replay_run(self, ctx: TenantContext, run_id: str) -> dict[str, object]:
        run = self._tenant_run(ctx, run_id)
        run["replay_count"] = int(run.get("replay_count", 0)) + 1
        self._put(run)
        self._event(ctx, RUN_REPLAYED, run_id, {"replay_count": run["replay_count"]})
        return _public_run(run)

    def resume_run(self, ctx: TenantContext, run_id: str) -> dict[str, object]:
        run = self._tenant_run(ctx, run_id)
        if run["status"] == "completed":
            return _public_run(run)
        run["status"] = "running"
        run["error"] = ""
        run["failed_step"] = ""
        run["resume_count"] = int(run.get("resume_count", 0)) + 1
        for step in WORKFLOW_STEPS:
            step_record = dict(run["steps"][step])
            if step_record["status"] == STEP_FAILED:
                step_record["status"] = STEP_PENDING
                step_record["error"] = ""
                run["steps"][step] = step_record
        self._put(run)
        self._event(ctx, RUN_RESUMED, run_id, {"resume_count": run["resume_count"]})
        return self._execute(ctx, run)

    def portal(self, ctx: TenantContext, run_id: str) -> dict[str, object]:
        run = self._tenant_run(ctx, run_id)
        self._event(ctx, PORTAL_STATUS_VIEWED, run_id, {})
        return {
            "run_id": run_id,
            "portal": deepcopy(run.get("portal", {})),
            "customer_status": deepcopy(run.get("customer_status", {})),
        }

    def _execute(self, ctx: TenantContext, run: dict[str, object]) -> dict[str, object]:
        step_handlers: dict[str, Callable[[TenantContext, dict[str, object]], dict[str, object]]] = {
            "lead": self._step_lead,
            "estimate": self._step_estimate,
            "proposal": self._step_proposal,
            "job": self._step_job,
            "schedule": self._step_schedule,
            "cost_profitability": self._step_cost_profitability,
            "invoice_payment": self._step_invoice_payment,
            "portal_status": self._step_portal_status,
        }
        for step in WORKFLOW_STEPS:
            record = dict(run["steps"][step])
            if record["status"] == STEP_COMPLETED:
                continue
            run["steps"][step] = {**record, "status": STEP_RUNNING, "error": ""}
            self._put(run)
            self._event(ctx, STEP_STARTED, str(run["run_id"]), {"step": step})
            try:
                output = step_handlers[step](ctx, run)
            except Exception as exc:
                run["steps"][step] = {**record, "status": STEP_FAILED, "error": str(exc)}
                run["status"] = "failed"
                run["error"] = str(exc)
                run["failed_step"] = step
                self._put(run)
                self._event(ctx, STEP_FAILED_EVENT, str(run["run_id"]), {"step": step, "error": str(exc)})
                self._event(ctx, RUN_FAILED, str(run["run_id"]), {"failed_step": step})
                return _public_run(run)
            run["steps"][step] = {"status": STEP_COMPLETED, "output": output, "error": ""}
            self._merge_entity_ids(run, output)
            self._put(run)
            self._event(ctx, STEP_COMPLETED_EVENT, str(run["run_id"]), {"step": step})

        run["status"] = "completed"
        run["error"] = ""
        run["failed_step"] = ""
        self._put(run)
        self._event(ctx, RUN_COMPLETED, str(run["run_id"]), {"entity_ids": run["entity_ids"]})
        return _public_run(run)

    def _step_lead(self, ctx: TenantContext, run: dict[str, object]) -> dict[str, object]:
        payload = dict(run["payload"])
        lead = self.service.create_lead(ctx, dict(payload["lead"]))
        for status in ("contacted", "estimate_scheduled", "proposal_sent", "won"):
            lead = self.service.update_lead(ctx, lead.lead_id, {"status": status})
        customer_payload = dict(dict(payload.get("proposal", {})).get("customer", {}))
        customer = self.service.convert_lead(ctx, lead.lead_id, customer_payload)
        return {
            "lead_id": lead.lead_id,
            "customer_id": customer.customer_id,
            "lead": lead.as_dict(),
            "customer": customer.as_dict(),
        }

    def _step_estimate(self, ctx: TenantContext, run: dict[str, object]) -> dict[str, object]:
        estimate = self.service.create_estimate(ctx, dict(dict(run["payload"])["estimate"]))
        return {"estimate_id": estimate.estimate_id, "estimate": estimate.as_dict()}

    def _step_proposal(self, ctx: TenantContext, run: dict[str, object]) -> dict[str, object]:
        payload = dict(run["payload"])
        proposal_payload = dict(payload["proposal"])
        proposal_payload["estimate_id"] = dict(run["entity_ids"])["estimate_id"]
        proposal_payload["customer"] = dict(run["steps"]["lead"]["output"])["customer"]
        proposal = self.service.create_proposal(ctx, proposal_payload)
        return {"proposal_id": proposal.proposal_id, "proposal": proposal.as_dict()}

    def _step_job(self, ctx: TenantContext, run: dict[str, object]) -> dict[str, object]:
        payload = dict(run["payload"])
        job_payload = dict(payload["job"])
        job_payload["proposal_id"] = dict(run["entity_ids"])["proposal_id"]
        job = self.service.create_job(ctx, job_payload)
        return {"job_id": job.job_id, "job": job.as_dict()}

    def _step_schedule(self, ctx: TenantContext, run: dict[str, object]) -> dict[str, object]:
        payload = dict(run["payload"])
        schedule_payload = dict(payload["schedule"])
        schedule_payload["job_id"] = dict(run["entity_ids"])["job_id"]
        schedule = self.service.create_schedule(ctx, schedule_payload)
        self.service.add_daily_log(ctx, str(dict(run["entity_ids"])["job_id"]), dict(payload["daily_log"]))
        return {"schedule_id": schedule.schedule_id, "schedule": schedule.as_dict()}

    def _step_cost_profitability(
        self,
        ctx: TenantContext,
        run: dict[str, object],
    ) -> dict[str, object]:
        job_id = str(dict(run["entity_ids"])["job_id"])
        cost = self.service.record_job_cost(ctx, job_id, dict(dict(run["payload"])["cost"]))
        profitability = self.service.job_profitability(ctx, job_id)
        output = {
            "cost_record_id": cost.cost_record_id,
            "cost": cost.as_dict(),
            "profitability": profitability.as_dict(),
        }
        run["financial_summary"] = {
            "actual_margin_percentage": profitability.actual_margin_percentage,
            "actual_gross_profit": profitability.actual_gross_profit,
            "actual_cost": profitability.actual_cost,
            "contracted_revenue": profitability.contracted_revenue,
            "financial_hash": profitability.financial_hash,
        }
        return output

    def _step_invoice_payment(self, ctx: TenantContext, run: dict[str, object]) -> dict[str, object]:
        payload = dict(run["payload"])
        invoice_payload = dict(payload["invoice"])
        invoice_payload["job_id"] = dict(run["entity_ids"])["job_id"]
        invoice = self.service.create_invoice(ctx, invoice_payload)
        invoice = self.service.pay_invoice(ctx, invoice.invoice_id, dict(payload["payment"]))
        self._event(ctx, INVOICE_PAYMENT_GENERATED, str(run["run_id"]), {"invoice_id": invoice.invoice_id})
        return {"invoice_id": invoice.invoice_id, "invoice": invoice.as_dict()}

    def _step_portal_status(self, ctx: TenantContext, run: dict[str, object]) -> dict[str, object]:
        payload = dict(run["payload"])
        message_payload = dict(payload["message"])
        message_payload["customer_id"] = dict(run["entity_ids"])["customer_id"]
        message_payload["job_id"] = dict(run["entity_ids"])["job_id"]
        message = self.service.record_customer_message(ctx, message_payload)
        generated_date = str(payload["generated_date"])
        portal = self.service.customer_portal_view(
            ctx,
            str(dict(run["entity_ids"])["customer_id"]),
            generated_date,
        )
        customer_status = self.service.customer_job_status(
            ctx,
            str(dict(run["entity_ids"])["job_id"]),
            generated_date,
        )
        owner_summary = self.service.owner_financial_summary(ctx, generated_date)
        run["portal"] = portal.as_dict()
        run["customer_status"] = customer_status
        run["financial_summary"] = {
            **dict(run.get("financial_summary", {})),
            "owner_summary": owner_summary,
        }
        return {
            "message_id": message.message_id,
            "portal_view_id": portal.portal_view_id,
            "message": message.as_dict(),
            "portal": portal.as_dict(),
            "customer_status": customer_status,
            "owner_summary": owner_summary,
        }

    def _merge_entity_ids(self, run: dict[str, object], output: dict[str, object]) -> None:
        entity_ids = dict(run.get("entity_ids", {}))
        for key, value in output.items():
            if key.endswith("_id") and isinstance(value, str):
                entity_ids[key] = value
        run["entity_ids"] = entity_ids

    def _tenant_run(self, ctx: TenantContext, run_id: str) -> dict[str, object]:
        run = self.persistence.get(MVP_RUNS, run_id)
        if not run or run.get("tenant_id") != ctx.tenant_id:
            raise KeyError("MVP run not found")
        return run

    def _get_idempotent(self, ctx: TenantContext, idempotency_key: str) -> dict[str, object] | None:
        index = self.persistence.get(MVP_IDEMPOTENCY, self._idempotency_index_key(ctx, idempotency_key))
        if not index:
            return None
        run = self.persistence.get(MVP_RUNS, str(index["run_id"]))
        return _public_run(run) if run else None

    def _idempotency_index_key(self, ctx: TenantContext, idempotency_key: str) -> str:
        return f"{ctx.tenant_id}:{idempotency_key}"

    def _put(self, run: dict[str, object]) -> None:
        self.persistence.put(MVP_RUNS, str(run["run_id"]), run)

    def _event(
        self,
        ctx: TenantContext,
        event_type: str,
        subject_id: str,
        payload: dict[str, object],
    ) -> None:
        self.event_store.append(
            event_type,
            subject_id,
            {
                "tenant_id": ctx.tenant_id,
                "organization_id": ctx.organization_id,
                "actor_id": ctx.principal_id,
                **payload,
            },
        )


def run_mvp_workflow(
    service: RenovationFoundationService,
    ctx: TenantContext,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    workflow = RenovationMvpWorkflow(service, service.persistence, service.event_store)
    return workflow.create_run(ctx, payload or {})


def _normalized_payload(request: dict[str, object]) -> dict[str, object]:
    overrides = dict(request.get("payload", request))
    for meta_key in ("run_id", "idempotency_key"):
        overrides.pop(meta_key, None)
    if "project" in overrides:
        proposal = dict(overrides.get("proposal", {}))
        proposal["project"] = overrides.pop("project")
        overrides["proposal"] = proposal
    if "customer" in overrides:
        proposal = dict(overrides.get("proposal", {}))
        proposal["customer"] = overrides.pop("customer")
        overrides["proposal"] = proposal
    return _deep_merge(DEFAULT_MVP_PAYLOAD, overrides)


def _idempotency_key(request: dict[str, object]) -> str:
    return str(request.get("idempotency_key", "")).strip()


def _stable_run_id(
    ctx: TenantContext,
    idempotency_key: str,
    payload: dict[str, object],
) -> str:
    if not idempotency_key:
        return f"mvp-run-{uuid4().hex}"
    digest = sha256(
        json.dumps(
            {"tenant_id": ctx.tenant_id, "idempotency_key": idempotency_key, "payload": payload},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return f"mvp-run-{digest[:24]}"


def _public_run(run: dict[str, object]) -> dict[str, object]:
    return {
        "run_id": run["run_id"],
        "tenant_id": run["tenant_id"],
        "status": run["status"],
        "idempotency_key": run.get("idempotency_key", ""),
        "steps": deepcopy(run["steps"]),
        "entity_ids": deepcopy(run.get("entity_ids", {})),
        "financial_summary": deepcopy(run.get("financial_summary", {})),
        "portal": deepcopy(run.get("portal", {})),
        "customer_status": deepcopy(run.get("customer_status", {})),
        "error": run.get("error", ""),
        "failed_step": run.get("failed_step", ""),
        "replay_count": run.get("replay_count", 0),
        "resume_count": run.get("resume_count", 0),
    }


def _deep_merge(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = deepcopy(value)
    return merged
