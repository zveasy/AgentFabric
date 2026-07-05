"""Operator cockpit facade for RenovationOS persisted domain records."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json

from agentfabric.enterprise import TenantContext
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore

from .models import Customer
from .saas import (
    LocalCalendarProvider,
    LocalNotificationProvider,
    LocalPaymentProvider,
    RenovationPdfService,
)
from .service import RenovationFoundationService


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix: str, tenant_id: str, payload: dict[str, object]) -> str:
    digest = sha256(
        json.dumps({"tenant_id": tenant_id, "payload": payload}, sort_keys=True, default=str).encode()
    ).hexdigest()
    return f"{prefix}-{digest[:20]}"


class RenovationOperatorCockpit:
    def __init__(
        self,
        service: RenovationFoundationService,
        persistence: PersistenceStore,
        event_store: EventStore,
        *,
        pdf_service: RenovationPdfService | None = None,
        notification_provider: LocalNotificationProvider | None = None,
        calendar_provider: LocalCalendarProvider | None = None,
        payment_provider: LocalPaymentProvider | None = None,
    ) -> None:
        self.service = service
        self.persistence = persistence
        self.event_store = event_store
        self.pdf_service = pdf_service or RenovationPdfService()
        self.notification_provider = notification_provider or LocalNotificationProvider()
        self.calendar_provider = calendar_provider or LocalCalendarProvider()
        self.payment_provider = payment_provider or LocalPaymentProvider()

    def company_profile(self, ctx: TenantContext) -> dict[str, object]:
        key = f"{ctx.tenant_id}:company"
        record = self.persistence.get("renovation_settings", key)
        if record is None:
            return self.update_company_profile(
                ctx,
                {
                    "company_name": "Company Branding Placeholder",
                    "logo_label": "Logo Placeholder",
                    "proposal_terms": "Payment schedule, warranty, and change orders are subject to written approval.",
                    "invoice_terms": "Payment due by the stated due date.",
                },
            )
        if record.get("tenant_id") != ctx.tenant_id:
            raise KeyError("company profile not found")
        return record

    def update_company_profile(self, ctx: TenantContext, payload: dict[str, object]) -> dict[str, object]:
        now = utc_now()
        key = f"{ctx.tenant_id}:company"
        record = {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": ctx.principal_id,
            "created_at": now,
            "updated_at": now,
            "artifact": {
                "company_name": str(payload.get("company_name", "Company Branding Placeholder")),
                "logo_label": str(payload.get("logo_label", "Logo Placeholder")),
                "proposal_terms": str(payload.get("proposal_terms", "")),
                "invoice_terms": str(payload.get("invoice_terms", "")),
                "address": str(payload.get("address", "")),
                "phone": str(payload.get("phone", "")),
                "email": str(payload.get("email", "")),
            },
        }
        self.persistence.put("renovation_settings", key, record)
        self._event(ctx, "renovation.operator.settings.updated", key, {"settings_id": key})
        return record

    def account_context(self, ctx: TenantContext) -> dict[str, object]:
        role = self._primary_role(ctx)
        return {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "principal_id": ctx.principal_id,
            "role": role,
            "roles": list(ctx.roles),
            "permissions": {
                "can_view": True,
                "can_operate": role in {"owner", "operator"},
                "can_manage": role == "owner",
            },
        }

    def assign_account_role(self, ctx: TenantContext, payload: dict[str, object]) -> dict[str, object]:
        if self._primary_role(ctx) != "owner":
            raise PermissionError("owner role required")
        role = str(payload["role"])
        if role not in {"owner", "operator", "viewer"}:
            raise ValueError("role must be owner, operator, or viewer")
        account_id = str(payload.get("account_id") or payload.get("principal_id"))
        if not account_id:
            raise ValueError("account_id is required")
        now = utc_now()
        record = {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": ctx.principal_id,
            "created_at": now,
            "updated_at": now,
            "artifact": {
                "account_id": account_id,
                "principal_id": str(payload.get("principal_id", account_id)),
                "name": str(payload.get("name", "")),
                "email": str(payload.get("email", "")),
                "role": role,
                "status": str(payload.get("status", "active")),
            },
        }
        self.persistence.put("renovation_accounts", f"{ctx.tenant_id}:{account_id}", record)
        self._event(ctx, "renovation.operator.account.role_assigned", account_id, {"account_id": account_id, "role": role})
        return record

    def list_accounts(self, ctx: TenantContext, filters: dict[str, object] | None = None) -> dict[str, object]:
        return self._list(ctx, "renovation_accounts", filters)

    def create_customer(self, ctx: TenantContext, payload: dict[str, object]) -> dict[str, object]:
        customer = Customer(
            customer_id=str(payload.get("customer_id") or stable_id("customer", ctx.tenant_id, payload)),
            name=str(payload["name"]),
            email=str(payload.get("email", "")),
            phone=str(payload.get("phone", "")),
            address=str(payload.get("address", payload.get("property_address", ""))),
        )
        return self._put_artifact(ctx, "renovation_customers", customer.customer_id, customer.as_dict(), "customer.created")

    def list_customers(self, ctx: TenantContext, filters: dict[str, object] | None = None) -> dict[str, object]:
        return self._list(ctx, "renovation_customers", filters)

    def get_customer(self, ctx: TenantContext, customer_id: str) -> dict[str, object]:
        return self._artifact(ctx, "renovation_customers", customer_id)

    def create_lead(self, ctx: TenantContext, payload: dict[str, object]) -> dict[str, object]:
        lead = self.service.create_lead(ctx, payload)
        self._event(ctx, "renovation.operator.lead.created", lead.lead_id, {"lead_id": lead.lead_id})
        return self._record_for("renovation_leads", lead.lead_id)

    def list_leads(self, ctx: TenantContext, filters: dict[str, object] | None = None) -> dict[str, object]:
        return self._list(ctx, "renovation_leads", filters)

    def convert_lead(self, ctx: TenantContext, lead_id: str, payload: dict[str, object]) -> dict[str, object]:
        customer = self.service.convert_lead(ctx, lead_id, payload)
        self._event(ctx, "renovation.operator.lead.converted", lead_id, {"lead_id": lead_id, "customer_id": customer.customer_id})
        return {"lead": self.service.get_lead(ctx, lead_id).as_dict(), "customer": customer.as_dict()}

    def create_estimate(self, ctx: TenantContext, payload: dict[str, object]) -> dict[str, object]:
        estimate = self.service.create_estimate(ctx, payload)
        self._event(ctx, "renovation.operator.estimate.created", estimate.estimate_id, {"estimate_id": estimate.estimate_id})
        return self._record_for("renovation_estimates", estimate.estimate_id)

    def list_estimates(self, ctx: TenantContext, filters: dict[str, object] | None = None) -> dict[str, object]:
        return self._list(ctx, "renovation_estimates", filters)

    def approve_estimate(self, ctx: TenantContext, estimate_id: str) -> dict[str, object]:
        record = self._tenant_record(ctx, "renovation_estimates", estimate_id)
        record["status"] = "approved"
        record["updated_at"] = utc_now()
        self.persistence.put("renovation_estimates", estimate_id, record)
        self._event(ctx, "renovation.operator.estimate.approved", estimate_id, {"estimate_id": estimate_id})
        return record

    def create_proposal(self, ctx: TenantContext, payload: dict[str, object]) -> dict[str, object]:
        prepared = dict(payload)
        if "customer" not in prepared and prepared.get("customer_id"):
            prepared["customer"] = self.get_customer(ctx, str(prepared["customer_id"]))["artifact"]
        if "project" not in prepared:
            estimate = self.service.get_estimate(ctx, str(prepared["estimate_id"]))
            prepared["project"] = {
                "project_id": estimate.project_id,
                "title": str(prepared.get("title", estimate.project_id)),
                "property_address": str(prepared.get("property_address", "")),
                "notes": str(prepared.get("notes", "")),
            }
        proposal = self.service.create_proposal(ctx, prepared)
        self._event(ctx, "renovation.operator.proposal.created", proposal.proposal_id, {"proposal_id": proposal.proposal_id})
        return self._record_for("renovation_proposals", proposal.proposal_id)

    def list_proposals(self, ctx: TenantContext, filters: dict[str, object] | None = None) -> dict[str, object]:
        return self._list(ctx, "renovation_proposals", filters)

    def accept_proposal(self, ctx: TenantContext, proposal_id: str, payload: dict[str, object]) -> dict[str, object]:
        record = self._tenant_record(ctx, "renovation_proposals", proposal_id)
        record["status"] = "accepted"
        record["accepted_at"] = utc_now()
        record["acceptance"] = payload
        record["updated_at"] = utc_now()
        self.persistence.put("renovation_proposals", proposal_id, record)
        self._event(ctx, "renovation.operator.proposal.accepted", proposal_id, {"proposal_id": proposal_id})
        return record

    def create_job(self, ctx: TenantContext, payload: dict[str, object]) -> dict[str, object]:
        prepared = {"accepted": True, **payload}
        job = self.service.create_job(ctx, prepared)
        self._event(ctx, "renovation.operator.job.created", job.job_id, {"job_id": job.job_id})
        return self._record_for("renovation_jobs", job.job_id)

    def list_jobs(self, ctx: TenantContext, filters: dict[str, object] | None = None) -> dict[str, object]:
        return self._list(ctx, "renovation_jobs", filters)

    def update_job_status(self, ctx: TenantContext, job_id: str, payload: dict[str, object]) -> dict[str, object]:
        job = self.service.update_job(ctx, job_id, {"status": str(payload["status"]), **payload})
        self._event(ctx, "renovation.operator.job.status_changed", job_id, {"job_id": job_id, "status": job.status})
        return self._record_for("renovation_jobs", job_id)

    def create_schedule(self, ctx: TenantContext, job_id: str, payload: dict[str, object]) -> dict[str, object]:
        schedule = self.service.create_schedule(ctx, {"job_id": job_id, **payload})
        self._event(ctx, "renovation.operator.schedule_item.created", schedule.schedule_id, {"job_id": job_id, "schedule_id": schedule.schedule_id})
        return self._record_for("renovation_schedules", schedule.schedule_id)

    def list_job_schedules(self, ctx: TenantContext, job_id: str, filters: dict[str, object] | None = None) -> dict[str, object]:
        return self._list_by(ctx, "renovation_schedules", "job_id", job_id, filters)

    def list_schedules(self, ctx: TenantContext, filters: dict[str, object] | None = None) -> dict[str, object]:
        return self._list(ctx, "renovation_schedules", filters)

    def create_cost(self, ctx: TenantContext, job_id: str, payload: dict[str, object]) -> dict[str, object]:
        cost = self.service.record_job_cost(ctx, job_id, payload)
        self._event(ctx, "renovation.operator.cost_item.created", cost.cost_record_id, {"job_id": job_id, "cost_record_id": cost.cost_record_id, "amount": cost.amount})
        return self._record_for("renovation_job_costs", cost.cost_record_id)

    def list_costs(self, ctx: TenantContext, job_id: str, filters: dict[str, object] | None = None) -> dict[str, object]:
        return self._list_by(ctx, "renovation_job_costs", "job_id", job_id, filters)

    def profitability(self, ctx: TenantContext, job_id: str) -> dict[str, object]:
        scorecard = self.service.job_profitability(ctx, job_id)
        return scorecard.as_dict()

    def create_invoice(self, ctx: TenantContext, job_id: str, payload: dict[str, object]) -> dict[str, object]:
        invoice = self.service.create_invoice(ctx, {**payload, "job_id": job_id})
        self._event(ctx, "renovation.operator.invoice.created", invoice.invoice_id, {"job_id": job_id, "invoice_id": invoice.invoice_id, "total": invoice.total})
        return self._record_for("renovation_invoices", invoice.invoice_id)

    def list_invoices(self, ctx: TenantContext, job_id: str, filters: dict[str, object] | None = None) -> dict[str, object]:
        return self._list_by(ctx, "renovation_invoices", "job_id", job_id, filters)

    def list_all_invoices(self, ctx: TenantContext, filters: dict[str, object] | None = None) -> dict[str, object]:
        return self._list(ctx, "renovation_invoices", filters)

    def record_payment(self, ctx: TenantContext, invoice_id: str, payload: dict[str, object]) -> dict[str, object]:
        invoice = self.service.pay_invoice(ctx, invoice_id, payload)
        self._event(ctx, "renovation.operator.payment.recorded", invoice_id, {"invoice_id": invoice_id, "paid_amount": invoice.paid_amount})
        record = self._record_for("renovation_invoices", invoice_id)
        self.payment_status(ctx, invoice_id, "paid" if invoice.outstanding_balance <= 0 else "partial")
        return record

    def portal(self, ctx: TenantContext, job_id: str) -> dict[str, object]:
        generated_date = datetime.now(timezone.utc).date().isoformat()
        status = self.service.customer_job_status(ctx, job_id, generated_date)
        self._event(ctx, "renovation.operator.portal.viewed", job_id, {"job_id": job_id})
        return status

    def metrics(self, ctx: TenantContext) -> dict[str, object]:
        leads = [r["artifact"] for r in self.persistence.list_tenant("renovation_leads", ctx.tenant_id)]
        jobs = [r["artifact"] for r in self.persistence.list_tenant("renovation_jobs", ctx.tenant_id)]
        estimates = [r["artifact"] for r in self.persistence.list_tenant("renovation_estimates", ctx.tenant_id)]
        invoices = [r["artifact"] for r in self.persistence.list_tenant("renovation_invoices", ctx.tenant_id)]
        costs = [r["artifact"] for r in self.persistence.list_tenant("renovation_job_costs", ctx.tenant_id)]
        estimated_revenue = sum(float(e.get("total", e.get("grand_total", 0))) for e in estimates)
        invoiced_revenue = sum(float(i.get("total", 0)) for i in invoices)
        paid_revenue = sum(float(i.get("paid_amount", 0)) for i in invoices)
        total_costs = sum(float(c.get("amount", 0)) for c in costs)
        gross_profit = invoiced_revenue - total_costs
        active_jobs = [j for j in jobs if j.get("status") not in {"completed", "cancelled"}]
        completed_jobs = [j for j in jobs if j.get("status") == "completed"]
        margins = []
        for job in jobs:
            try:
                score = self.service.job_profitability(ctx, str(job["job_id"]))
                margins.append(score.actual_margin_percentage)
            except Exception:
                pass
        metrics = {
            "total_leads": len(leads),
            "converted_leads": len([lead for lead in leads if lead.get("customer_id")]),
            "active_jobs": len(active_jobs),
            "completed_jobs": len(completed_jobs),
            "estimated_revenue": round(estimated_revenue, 2),
            "invoiced_revenue": round(invoiced_revenue, 2),
            "paid_revenue": round(paid_revenue, 2),
            "outstanding_receivables": round(invoiced_revenue - paid_revenue, 2),
            "total_costs": round(total_costs, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_margin_percentage": round((gross_profit / invoiced_revenue * 100) if invoiced_revenue else 0, 2),
            "jobs_at_risk": len([j for j in jobs if j.get("status") in {"delayed", "at_risk"}]),
            "average_estimate_value": round((estimated_revenue / len(estimates)) if estimates else 0, 2),
            "average_job_margin": round((sum(margins) / len(margins)) if margins else 0, 2),
        }
        self._event(ctx, "renovation.operator.metrics.viewed", ctx.tenant_id, {})
        return metrics

    def proposal_pdf(self, ctx: TenantContext, proposal_id: str) -> tuple[bytes, str]:
        record = self._tenant_record(ctx, "renovation_proposals", proposal_id)
        company = dict(self.company_profile(ctx).get("artifact", {}))
        payload = self.pdf_service.proposal(record, company)
        self._event(ctx, "renovation.operator.proposal.pdf_exported", proposal_id, {"proposal_id": proposal_id})
        return payload, f"{proposal_id}.pdf"

    def invoice_pdf(self, ctx: TenantContext, invoice_id: str) -> tuple[bytes, str]:
        record = self._tenant_record(ctx, "renovation_invoices", invoice_id)
        company = dict(self.company_profile(ctx).get("artifact", {}))
        links = [
            dict(item.get("artifact", {}))
            for item in self.persistence.list_tenant("renovation_payment_links", ctx.tenant_id)
            if dict(dict(item.get("artifact", {})).get("payload", {})).get("invoice_id") == invoice_id
        ]
        payload = self.pdf_service.invoice(record, company, links[-1] if links else None)
        self._event(ctx, "renovation.operator.invoice.pdf_exported", invoice_id, {"invoice_id": invoice_id})
        return payload, f"{invoice_id}.pdf"

    def record_attachment(
        self,
        ctx: TenantContext,
        attachment_record: dict[str, object],
    ) -> dict[str, object]:
        artifact = dict(attachment_record.get("artifact", {}))
        self._event(
            ctx,
            "renovation.operator.attachment.created",
            str(artifact.get("attachment_id", "attachment")),
            {
                "attachment_id": artifact.get("attachment_id"),
                "entity_type": artifact.get("entity_type"),
                "entity_id": artifact.get("entity_id"),
            },
        )
        return attachment_record

    def attachment_downloaded(self, ctx: TenantContext, attachment_id: str) -> None:
        self._event(ctx, "renovation.operator.attachment.downloaded", attachment_id, {"attachment_id": attachment_id})

    def attachment_archived(self, ctx: TenantContext, attachment_record: dict[str, object]) -> dict[str, object]:
        artifact = dict(attachment_record.get("artifact", {}))
        self._event(ctx, "renovation.operator.attachment.archived", str(artifact.get("attachment_id")), {"attachment_id": artifact.get("attachment_id")})
        return attachment_record

    def send_notification(self, ctx: TenantContext, event_type: str, payload: dict[str, object]) -> dict[str, object]:
        self._event(ctx, "renovation.operator.notification.send_attempted", event_type, {"notification_type": event_type, "channel": payload.get("channel", "email")})
        result = self.notification_provider.send(ctx.tenant_id, event_type, payload).as_dict()
        notification_id = str(result["reference_id"])
        record = self._stub_record(ctx, "notification", notification_id, result)
        self.persistence.put("renovation_notifications", notification_id, record)
        self._event(ctx, "renovation.operator.notification.queued", notification_id, {"notification_id": notification_id, "notification_type": event_type})
        if result.get("status") == "failed":
            self._event(ctx, "renovation.operator.notification.failed", notification_id, {"notification_id": notification_id, "failure_reason": result.get("failure_reason")})
            self._event(ctx, "renovation.operator.provider.failed", notification_id, {"provider_type": "notification", "failure_reason": result.get("failure_reason")})
        return record

    def list_notifications(self, ctx: TenantContext, filters: dict[str, object] | None = None) -> dict[str, object]:
        return self._list(ctx, "renovation_notifications", filters)

    def validate_provider(self, ctx: TenantContext, provider_type: str, payload: dict[str, object]) -> dict[str, object]:
        if provider_type == "notification":
            result = self.notification_provider.validate_config(payload)
        elif provider_type == "calendar":
            result = self.calendar_provider.validate_config(payload)
        elif provider_type == "payment":
            result = self.payment_provider.validate_config(payload)
        else:
            raise ValueError("unsupported renovation provider type")
        self._event(ctx, "renovation.operator.provider.validated", provider_type, {"provider_type": provider_type, "valid": result["valid"]})
        if not result["valid"]:
            self._event(ctx, "renovation.operator.provider.failed", provider_type, {"provider_type": provider_type, "failure_reason": "provider config validation failed"})
        return result

    def sync_schedule(self, ctx: TenantContext, schedule_id: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        schedule = dict(self._tenant_record(ctx, "renovation_schedules", schedule_id).get("artifact", {}))
        self._event(ctx, "renovation.operator.calendar.sync_attempted", schedule_id, {"schedule_id": schedule_id, "provider": dict(payload or {}).get("provider", "local")})
        result = self.calendar_provider.sync(ctx.tenant_id, schedule, payload).as_dict()
        sync_id = str(result["reference_id"])
        record = self._stub_record(ctx, "calendar_sync", sync_id, result)
        self.persistence.put("renovation_calendar_syncs", sync_id, record)
        self._event(ctx, "renovation.operator.schedule.synced", schedule_id, {"schedule_id": schedule_id, "sync_id": sync_id, "status": result["status"]})
        if result.get("status") == "failed":
            self._event(ctx, "renovation.operator.provider.failed", sync_id, {"provider_type": "calendar", "failure_reason": result.get("failure_reason")})
        return record

    def payment_link(self, ctx: TenantContext, invoice_id: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        invoice = dict(self._tenant_record(ctx, "renovation_invoices", invoice_id).get("artifact", {}))
        payload = payload or {}
        result = self.payment_provider.link(ctx.tenant_id, invoice, str(payload.get("idempotency_key") or "") or None, payload).as_dict()
        link_id = str(result["reference_id"])
        existing = self.persistence.get("renovation_payment_links", link_id)
        if existing is not None and existing.get("tenant_id") == ctx.tenant_id:
            return existing
        record = self._stub_record(ctx, "payment_link", link_id, result)
        self.persistence.put("renovation_payment_links", link_id, record)
        self._event(ctx, "renovation.operator.payment_link.created", invoice_id, {"invoice_id": invoice_id, "payment_link_id": link_id})
        return record

    def payment_status(
        self,
        ctx: TenantContext,
        invoice_id: str,
        status: str,
        provider_reference_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        self._tenant_record(ctx, "renovation_invoices", invoice_id)
        result = self.payment_provider.status(ctx.tenant_id, invoice_id, status, provider_reference_id, idempotency_key).as_dict()
        status_id = str(result["reference_id"])
        existing = self.persistence.get("renovation_payment_statuses", status_id)
        if existing is not None and existing.get("tenant_id") == ctx.tenant_id:
            return existing
        record = self._stub_record(ctx, "payment_status", status_id, result)
        self.persistence.put("renovation_payment_statuses", status_id, record)
        self._event(ctx, "renovation.operator.payment_status.updated", invoice_id, {"invoice_id": invoice_id, "payment_status": status})
        return record

    def list_payment_statuses(self, ctx: TenantContext, filters: dict[str, object] | None = None) -> dict[str, object]:
        return self._list(ctx, "renovation_payment_statuses", filters)

    def payment_webhook(self, ctx: TenantContext, payload: dict[str, object]) -> dict[str, object]:
        validation = self.payment_provider.validate_webhook(payload)
        if not validation["valid"]:
            invoice_id = str(payload.get("invoice_id", "unknown"))
            self._event(ctx, "renovation.operator.payment_webhook.rejected", invoice_id, {"invoice_id": invoice_id, "failure_reason": validation.get("failure_reason")})
            self._event(ctx, "renovation.operator.provider.failed", invoice_id, {"provider_type": "payment", "failure_reason": validation.get("failure_reason")})
            raise ValueError(str(validation.get("failure_reason", "payment webhook rejected")))
        invoice_id = str(payload["invoice_id"])
        mapped_status = self.payment_provider.map_webhook_status(payload)
        record = self.payment_status(
            ctx,
            invoice_id,
            mapped_status,
            str(payload.get("provider_reference_id", "")) or None,
            str(payload.get("idempotency_key", "")) or None,
        )
        self._event(
            ctx,
            "renovation.operator.payment_webhook.received",
            invoice_id,
            {"invoice_id": invoice_id, "status": mapped_status, "provider_event_type": payload.get("event_type") or payload.get("type")},
        )
        return record

    def _put_artifact(self, ctx: TenantContext, collection: str, key: str, artifact: dict[str, object], event: str) -> dict[str, object]:
        now = utc_now()
        record = {"tenant_id": ctx.tenant_id, "organization_id": ctx.organization_id, "created_by": ctx.principal_id, "created_at": now, "updated_at": now, "artifact": artifact}
        self.persistence.put(collection, key, record)
        self._event(ctx, f"renovation.operator.{event}", key, {"record_id": key})
        return record

    def _stub_record(self, ctx: TenantContext, record_type: str, key: str, artifact: dict[str, object]) -> dict[str, object]:
        now = utc_now()
        return {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": ctx.principal_id,
            "created_at": now,
            "updated_at": now,
            "record_type": record_type,
            "artifact": artifact,
        }

    def _record_for(self, collection: str, key: str) -> dict[str, object]:
        record = self.persistence.get(collection, key)
        if record is None:
            raise KeyError(f"{key} not found")
        record.setdefault("created_at", utc_now())
        record.setdefault("updated_at", record["created_at"])
        self.persistence.put(collection, key, record)
        return record

    def _tenant_record(self, ctx: TenantContext, collection: str, key: str) -> dict[str, object]:
        record = self.persistence.get(collection, key)
        if record is None or record.get("tenant_id") != ctx.tenant_id:
            raise KeyError(f"{key} not found")
        return record

    def _artifact(self, ctx: TenantContext, collection: str, key: str) -> dict[str, object]:
        return self._tenant_record(ctx, collection, key)

    def _list(self, ctx: TenantContext, collection: str, filters: dict[str, object] | None = None) -> dict[str, object]:
        items = self.persistence.list_tenant(collection, ctx.tenant_id)
        return self._filter_page(items, filters)

    def _list_by(
        self,
        ctx: TenantContext,
        collection: str,
        field: str,
        value: str,
        filters: dict[str, object] | None = None,
    ) -> dict[str, object]:
        items = [
            item
            for item in self.persistence.list_tenant(collection, ctx.tenant_id)
            if item.get(field) == value or dict(item.get("artifact", {})).get(field) == value
        ]
        return self._filter_page(items, filters)

    def _filter_page(self, items: list[dict[str, object]], filters: dict[str, object] | None = None) -> dict[str, object]:
        filters = filters or {}
        search = str(filters.get("search", "") or "").strip().lower()
        status = str(filters.get("status", "") or "").strip().lower()
        customer_id = str(filters.get("customer_id", "") or "").strip()
        date_from = str(filters.get("date_from", "") or "").strip()
        date_to = str(filters.get("date_to", "") or "").strip()
        if search:
            items = [item for item in items if search in json.dumps(item, sort_keys=True, default=str).lower()]
        if status:
            items = [
                item
                for item in items
                if str(item.get("status") or dict(item.get("artifact", {})).get("status") or "").lower() == status
            ]
        if customer_id:
            items = [item for item in items if str(dict(item.get("artifact", {})).get("customer_id", "")) == customer_id]
        if date_from or date_to:
            items = [item for item in items if self._record_in_date_range(item, date_from, date_to)]
        total = len(items)
        limit = max(1, min(int(filters.get("limit", 50) or 50), 200))
        offset = max(0, int(filters.get("offset", 0) or 0))
        paged = items[offset : offset + limit]
        next_offset = offset + limit if offset + limit < total else None
        applied = {
            "search": search,
            "status": status,
            "customer_id": customer_id,
            "date_from": date_from,
            "date_to": date_to,
        }
        return {"items": paged, "total": total, "limit": limit, "offset": offset, "next_offset": next_offset, "filters": applied}

    def _record_in_date_range(self, item: dict[str, object], date_from: str, date_to: str) -> bool:
        artifact = dict(item.get("artifact", {}))
        candidates = [
            item.get("created_at"),
            item.get("updated_at"),
            artifact.get("created_date"),
            artifact.get("invoice_date"),
            artifact.get("due_date"),
            artifact.get("start_date"),
            artifact.get("cost_date"),
            artifact.get("payment_date"),
        ]
        values = [str(value)[:10] for value in candidates if value]
        if not values:
            return False
        return any((not date_from or value >= date_from) and (not date_to or value <= date_to) for value in values)

    def _event(self, ctx: TenantContext, event_type: str, aggregate_id: str, payload: dict[str, object]) -> None:
        self.event_store.append(event_type, aggregate_id, {"tenant_id": ctx.tenant_id, "organization_id": ctx.organization_id, "actor_id": ctx.principal_id, **payload})

    def _primary_role(self, ctx: TenantContext) -> str:
        scopes = set(ctx.roles)
        if {"tenant.manage", "rbac.assign_role"} & scopes:
            return "owner"
        if "renovation.operator.write" in scopes:
            return "operator"
        if "renovation.operator.read" in scopes:
            return "viewer"
        for role in ("owner", "operator", "viewer"):
            if role in ctx.roles:
                return role
        return ctx.roles[0] if ctx.roles else "viewer"
