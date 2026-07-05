"""Tenant-isolated RenovationOS Foundation service."""

from __future__ import annotations

from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError, NotFoundError
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore

from .change_orders import (
    ChangeOrder,
    ChangeOrderApproval,
    ChangeOrderLine,
    ChangeOrderService,
)
from .communications import (
    CommunicationService,
    CustomerMessage,
)
from .crews import Crew, CrewAssignment, CrewAvailability, CrewMember, CrewService
from .crm import (
    AppointmentRequest,
    CrmService,
    FollowUpTask,
    Opportunity,
    SiteVisit,
)
from .customer_portal import (
    DEFAULT_VISIBILITY_POLICY,
    CustomerPortalService,
    CustomerPortalView,
    CustomerVisibilityPolicy,
)
from .deliveries import DeliveryService, MaterialDelivery
from .documentation import (
    DailyLog,
    DocumentationService,
    FieldNote,
    IssueRecord,
    PhotoRecord,
)
from .estimate import EstimateService
from .events import (
    CASH_FLOW_FORECAST_GENERATED,
    CHANGE_ORDER_APPROVED,
    CHANGE_ORDER_CREATED,
    CHANGE_ORDER_EXPORTED,
    CHANGE_ORDER_REJECTED,
    CREW_ASSIGNED,
    CREW_AVAILABILITY_UPDATED,
    CREW_CREATED,
    CREW_UNASSIGNED,
    COST_OVERRUN_DETECTED,
    CUSTOMER_MESSAGE_RECORDED,
    CUSTOMER_PORTAL_VIEW_GENERATED,
    DAILY_LOG_CREATED,
    DELAY_DETECTED,
    ESTIMATE_CREATED,
    ESTIMATE_UPDATED,
    FIELD_NOTE_ADDED,
    FOLLOW_UP_TASK_CREATED,
    ISSUE_RECORD_ADDED,
    INVOICE_CREATED,
    INVOICE_PAID,
    JOB_CREATED,
    JOB_COST_RECORDED,
    JOB_UPDATED,
    LEAD_CONVERTED,
    LEAD_CREATED,
    LEAD_UPDATED,
    MARGIN_VARIANCE_DETECTED,
    MATERIAL_DELIVERY_CREATED,
    MATERIAL_DELIVERY_UPDATED,
    PHOTO_RECORD_ADDED,
    PAYABLE_CREATED,
    PAYABLE_PAID,
    PROFITABILITY_SCORECARD_GENERATED,
    APPOINTMENT_REQUESTED,
    OPPORTUNITY_CREATED,
    OPPORTUNITY_STAGE_CHANGED,
    PROPOSAL_EXPORTED,
    PROPOSAL_GENERATED,
    SCHEDULE_CREATED,
    SCHEDULE_RECALCULATED,
    SCHEDULE_UPDATED,
    SITE_VISIT_RECORDED,
)
from .finance import (
    ActualLaborCost,
    ActualMaterialCost,
    FinanceService,
    JobCostRecord,
    OverheadAllocation,
    SubcontractorCost,
)
from .invoicing import Invoice, InvoiceService, PaymentRecord, VendorPayable
from .leads import Lead, LeadService, LeadSource
from .jobs import Job, JobPhase, JobService
from .marketplace import RENOVATION_FOUNDATION_PACKAGE
from .models import (
    Customer,
    Estimate,
    LaborLine,
    MaterialLine,
    PaymentSchedule,
    Project,
    Proposal,
    ScopeItem,
    Timeline,
)
from .proposal import ProposalService
from .profitability import (
    CashFlowForecast,
    CashFlowWindow,
    CostOverrunAlert,
    MarginVariance,
    ProfitabilityScorecard,
    ProfitabilityService,
)
from .scheduling import (
    DelayImpact,
    PhaseDependency,
    Schedule,
    ScheduleConflict,
    SchedulePhase,
    SchedulingService,
)


class RenovationFoundationService:
    def __init__(self, persistence: PersistenceStore, event_store: EventStore) -> None:
        self.persistence = persistence
        self.event_store = event_store
        self.estimates = EstimateService()
        self.proposals = ProposalService()
        self.jobs = JobService()
        self.documentation = DocumentationService()
        self.change_orders = ChangeOrderService()
        self.scheduling = SchedulingService()
        self.crews = CrewService()
        self.deliveries = DeliveryService()
        self.finance = FinanceService()
        self.invoicing = InvoiceService()
        self.profitability = ProfitabilityService()
        self.leads = LeadService()
        self.crm = CrmService()
        self.communications = CommunicationService()
        self.customer_portal = CustomerPortalService()
        self.persistence.put(
            "renovation_marketplace_packages",
            str(RENOVATION_FOUNDATION_PACKAGE["package_id"]),
            {"tenant_id": "system", **RENOVATION_FOUNDATION_PACKAGE},
        )

    def create_estimate(self, ctx: TenantContext, payload: dict[str, object]) -> Estimate:
        ctx.require()
        estimate = self.estimates.create(ctx.tenant_id, payload)
        existing = self.persistence.get("renovation_estimates", estimate.estimate_id)
        record = {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": ctx.principal_id,
            "input": payload,
            "artifact": estimate.as_dict(),
        }
        self.persistence.put("renovation_estimates", estimate.estimate_id, record)
        self.event_store.append(
            ESTIMATE_UPDATED if existing else ESTIMATE_CREATED,
            estimate.estimate_id,
            {
                "tenant_id": ctx.tenant_id,
                "organization_id": ctx.organization_id,
                "estimate_id": estimate.estimate_id,
                "artifact_hash": _artifact_hash(estimate.export_json()),
            },
        )
        return estimate

    def get_estimate(self, ctx: TenantContext, estimate_id: str) -> Estimate:
        value = self._tenant_record(ctx, "renovation_estimates", estimate_id, "estimate")
        return _estimate_from_dict(dict(value["artifact"]))

    def replay_estimate(self, ctx: TenantContext, estimate_id: str) -> Estimate:
        value = self._tenant_record(ctx, "renovation_estimates", estimate_id, "estimate")
        replayed = self.estimates.create(ctx.tenant_id, dict(value["input"]))
        original = _estimate_from_dict(dict(value["artifact"]))
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation estimate replay diverged")
        return replayed

    def create_proposal(self, ctx: TenantContext, payload: dict[str, object]) -> Proposal:
        estimate = self.get_estimate(ctx, str(payload["estimate_id"]))
        proposal = self.proposals.create(ctx.tenant_id, estimate, payload)
        record = {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": ctx.principal_id,
            "input": payload,
            "artifact": proposal.as_dict(),
        }
        self.persistence.put("renovation_proposals", proposal.proposal_id, record)
        self.event_store.append(
            PROPOSAL_GENERATED,
            proposal.proposal_id,
            {
                "tenant_id": ctx.tenant_id,
                "organization_id": ctx.organization_id,
                "proposal_id": proposal.proposal_id,
                "estimate_id": estimate.estimate_id,
                "template_id": proposal.template_id,
                "template_version": proposal.template_version,
                "artifact_hash": _artifact_hash(proposal.export_json()),
            },
        )
        return proposal

    def get_proposal(self, ctx: TenantContext, proposal_id: str) -> Proposal:
        value = self._tenant_record(ctx, "renovation_proposals", proposal_id, "proposal")
        return _proposal_from_dict(dict(value["artifact"]))

    def replay_proposal(self, ctx: TenantContext, proposal_id: str) -> Proposal:
        value = self._tenant_record(ctx, "renovation_proposals", proposal_id, "proposal")
        payload = dict(value["input"])
        estimate = self.get_estimate(ctx, str(payload["estimate_id"]))
        replayed = self.proposals.create(ctx.tenant_id, estimate, payload)
        original = _proposal_from_dict(dict(value["artifact"]))
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation proposal replay diverged")
        return replayed

    def export_proposal(
        self,
        ctx: TenantContext,
        proposal_id: str,
        export_format: str = "json",
    ) -> dict[str, object]:
        proposal = self.get_proposal(ctx, proposal_id)
        if export_format == "json":
            content = proposal.export_json()
        elif export_format == "text":
            content = proposal.rendered_text
        else:
            raise ValueError("proposal export format must be json or text")
        export = {
            "tenant_id": ctx.tenant_id,
            "proposal_id": proposal_id,
            "format": export_format,
            "content": content,
            "artifact_hash": _artifact_hash(content),
            "template_id": proposal.template_id,
        }
        key = f"{proposal_id}:{export_format}"
        self.persistence.put("renovation_proposal_exports", key, export)
        self.event_store.append(
            PROPOSAL_EXPORTED,
            proposal_id,
            {
                "tenant_id": ctx.tenant_id,
                "proposal_id": proposal_id,
                "format": export_format,
                "artifact_hash": export["artifact_hash"],
            },
        )
        return export

    def marketplace_package(self) -> dict[str, object]:
        return dict(RENOVATION_FOUNDATION_PACKAGE)

    def create_job(self, ctx: TenantContext, payload: dict[str, object]) -> Job:
        proposal = self.get_proposal(ctx, str(payload["proposal_id"]))
        job = self.jobs.create(ctx.tenant_id, proposal, payload)
        record = self._record(ctx, payload, job.as_dict())
        self.persistence.put("renovation_jobs", job.job_id, record)
        self.event_store.append(
            JOB_CREATED,
            job.job_id,
            self._event_payload(
                ctx,
                job_id=job.job_id,
                proposal_id=job.proposal_id,
                artifact_hash=_artifact_hash(job.export_json()),
            ),
        )
        return job

    def get_job(self, ctx: TenantContext, job_id: str) -> Job:
        value = self._tenant_record(ctx, "renovation_jobs", job_id, "job")
        return _job_from_dict(dict(value["artifact"]))

    def update_job(self, ctx: TenantContext, job_id: str, payload: dict[str, object]) -> Job:
        current = self.get_job(ctx, job_id)
        updated = self.jobs.update(current, payload)
        existing = self._tenant_record(ctx, "renovation_jobs", job_id, "job")
        existing["artifact"] = updated.as_dict()
        existing["last_update"] = payload
        self.persistence.put("renovation_jobs", job_id, existing)
        self.event_store.append(
            JOB_UPDATED,
            job_id,
            self._event_payload(
                ctx,
                job_id=job_id,
                status=updated.status,
                current_phase=updated.current_phase,
                artifact_hash=_artifact_hash(updated.export_json()),
            ),
        )
        return updated

    def replay_job(self, ctx: TenantContext, job_id: str) -> Job:
        value = self._tenant_record(ctx, "renovation_jobs", job_id, "job")
        payload = dict(value["input"])
        proposal = self.get_proposal(ctx, str(payload["proposal_id"]))
        replayed = self.jobs.create(ctx.tenant_id, proposal, payload)
        if value.get("last_update"):
            replayed = self.jobs.update(replayed, dict(value["last_update"]))
        original = _job_from_dict(dict(value["artifact"]))
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation job replay diverged")
        return replayed

    def add_daily_log(self, ctx: TenantContext, job_id: str, payload: dict[str, object]) -> DailyLog:
        self.get_job(ctx, job_id)
        photos = tuple(
            self._persist_photo(ctx, job_id, dict(item))
            for item in payload.get("photos", ())
        )
        issues = tuple(
            self._persist_issue(ctx, job_id, dict(item))
            for item in payload.get("issues", ())
        )
        log = self.documentation.daily_log(ctx.tenant_id, job_id, payload, photos, issues)
        self.persistence.put(
            "renovation_daily_logs",
            log.daily_log_id,
            self._record(ctx, payload, log.as_dict()),
        )
        self.event_store.append(
            DAILY_LOG_CREATED,
            log.daily_log_id,
            self._event_payload(
                ctx,
                job_id=job_id,
                daily_log_id=log.daily_log_id,
                work_date=log.work_date,
                artifact_hash=_artifact_hash(log.export_json()),
            ),
        )
        self._emit_job_documentation_update(ctx, job_id, "daily_log", log.daily_log_id)
        return log

    def replay_daily_log(self, ctx: TenantContext, daily_log_id: str) -> DailyLog:
        value = self._tenant_record(
            ctx,
            "renovation_daily_logs",
            daily_log_id,
            "daily log",
        )
        original = _daily_log_from_dict(dict(value["artifact"]))
        photos = tuple(
            _photo_from_dict(
                dict(
                    self._tenant_record(
                        ctx,
                        "renovation_photo_records",
                        photo_id,
                        "photo record",
                    )["artifact"]
                )
            )
            for photo_id in original.photo_record_ids
        )
        issues = tuple(
            _issue_from_dict(
                dict(
                    self._tenant_record(
                        ctx,
                        "renovation_issue_records",
                        issue_id,
                        "issue record",
                    )["artifact"]
                )
            )
            for issue_id in original.issue_record_ids
        )
        replayed = self.documentation.daily_log(
            ctx.tenant_id,
            original.job_id,
            dict(value["input"]),
            photos,
            issues,
        )
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation daily log replay diverged")
        return replayed

    def add_field_note(self, ctx: TenantContext, job_id: str, payload: dict[str, object]) -> FieldNote:
        self.get_job(ctx, job_id)
        photos = tuple(
            self._persist_photo(ctx, job_id, dict(item))
            for item in payload.get("photos", ())
        )
        note = self.documentation.field_note(ctx.tenant_id, job_id, payload, photos)
        self.persistence.put(
            "renovation_field_notes",
            note.field_note_id,
            self._record(ctx, payload, note.as_dict()),
        )
        self.event_store.append(
            FIELD_NOTE_ADDED,
            note.field_note_id,
            self._event_payload(
                ctx,
                job_id=job_id,
                field_note_id=note.field_note_id,
                note_date=note.note_date,
                artifact_hash=_artifact_hash(note.export_json()),
            ),
        )
        self._emit_job_documentation_update(ctx, job_id, "field_note", note.field_note_id)
        return note

    def replay_field_note(self, ctx: TenantContext, field_note_id: str) -> FieldNote:
        value = self._tenant_record(
            ctx,
            "renovation_field_notes",
            field_note_id,
            "field note",
        )
        original = _field_note_from_dict(dict(value["artifact"]))
        photos = tuple(
            _photo_from_dict(
                dict(
                    self._tenant_record(
                        ctx,
                        "renovation_photo_records",
                        photo_id,
                        "photo record",
                    )["artifact"]
                )
            )
            for photo_id in original.photo_record_ids
        )
        replayed = self.documentation.field_note(
            ctx.tenant_id,
            original.job_id,
            dict(value["input"]),
            photos,
        )
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation field note replay diverged")
        return replayed

    def project_history(self, ctx: TenantContext, job_id: str) -> dict[str, object]:
        job = self.get_job(ctx, job_id)
        proposal = self.get_proposal(ctx, job.proposal_id)
        collections = {
            "daily_logs": "renovation_daily_logs",
            "field_notes": "renovation_field_notes",
            "photos": "renovation_photo_records",
            "issues": "renovation_issue_records",
            "change_orders": "renovation_change_orders",
            "approvals": "renovation_change_order_approvals",
            "change_order_exports": "renovation_change_order_exports",
            "schedules": "renovation_schedules",
            "crew_assignments": "renovation_crew_assignments",
            "material_deliveries": "renovation_material_deliveries",
            "delay_impacts": "renovation_delay_impacts",
            "schedule_summaries": "renovation_schedule_summaries",
            "job_costs": "renovation_job_costs",
            "invoices": "renovation_invoices",
            "payments": "renovation_payments",
            "payables": "renovation_payables",
            "profitability_scorecards": "renovation_profitability_scorecards",
            "margin_variances": "renovation_margin_variances",
            "cost_overrun_alerts": "renovation_cost_overrun_alerts",
            "customer_messages": "renovation_customer_messages",
            "communications": "renovation_communications",
        }
        history: dict[str, object] = {
            "job": job.as_dict(),
            "proposal": proposal.as_dict(),
            "estimate": proposal.estimate.as_dict(),
        }
        for label, collection in collections.items():
            history[label] = [
                item["artifact"] if "artifact" in item else item
                for item in self.persistence.list_tenant(collection, ctx.tenant_id)
                if item.get("job_id") == job_id
                or dict(item.get("artifact", {})).get("job_id") == job_id
            ]
        history["events"] = sorted(
            [
                {
                    "event_type": event.event_type,
                    "aggregate_id": event.aggregate_id,
                    "payload": event.payload,
                }
            for event in self.event_store.replay()
            if event.payload.get("tenant_id") == ctx.tenant_id
            and (event.payload.get("job_id") == job_id or event.aggregate_id == job_id)
            ],
            key=lambda item: _canonical(item),
        )
        history["history_hash"] = _artifact_hash(_canonical(history))
        return history

    def daily_summary(self, ctx: TenantContext, job_id: str, work_date: str) -> dict[str, object]:
        self.get_job(ctx, job_id)
        records = {
            "logs": self._job_artifacts(ctx, "renovation_daily_logs", job_id, "work_date", work_date),
            "notes": self._job_artifacts(ctx, "renovation_field_notes", job_id, "note_date", work_date),
            "photos": self._job_artifacts(ctx, "renovation_photo_records", job_id, "captured_date", work_date),
            "issues": self._job_artifacts(ctx, "renovation_issue_records", job_id, "reported_date", work_date),
        }
        summary = self.documentation.daily_summary(work_date, **records)
        self.persistence.put(
            "renovation_daily_summaries",
            f"{job_id}:{work_date}",
            {"tenant_id": ctx.tenant_id, "job_id": job_id, **summary},
        )
        return summary

    def create_change_order(self, ctx: TenantContext, payload: dict[str, object]) -> ChangeOrder:
        job = self.get_job(ctx, str(payload["job_id"]))
        if str(payload.get("source_type", "scope_change")) == "field_note":
            note = self._tenant_record(
                ctx,
                "renovation_field_notes",
                str(payload["source_reference"]),
                "field note",
            )
            if dict(note["artifact"]).get("job_id") != job.job_id:
                raise AuthorizationError("field note belongs to a different renovation job")
        proposal = self.get_proposal(ctx, job.proposal_id)
        estimate_record = self._tenant_record(
            ctx,
            "renovation_estimates",
            proposal.estimate.estimate_id,
            "estimate",
        )
        order = self.change_orders.create(
            ctx.tenant_id,
            job.job_id,
            proposal.proposal_id,
            proposal.estimate,
            dict(estimate_record["input"]),
            payload,
        )
        self.persistence.put(
            "renovation_change_orders",
            order.change_order_id,
            {
                **self._record(ctx, payload, order.as_dict()),
                "job_id": job.job_id,
            },
        )
        self.event_store.append(
            CHANGE_ORDER_CREATED,
            order.change_order_id,
            self._event_payload(
                ctx,
                job_id=job.job_id,
                change_order_id=order.change_order_id,
                status=order.status,
                template_id=order.template_id,
                artifact_hash=_artifact_hash(order.export_json()),
            ),
        )
        return order

    def get_change_order(self, ctx: TenantContext, change_order_id: str) -> ChangeOrder:
        value = self._tenant_record(
            ctx,
            "renovation_change_orders",
            change_order_id,
            "change order",
        )
        return _change_order_from_dict(dict(value["artifact"]))

    def decide_change_order(
        self,
        ctx: TenantContext,
        change_order_id: str,
        decision: str,
        payload: dict[str, object],
    ) -> ChangeOrder:
        order = self.get_change_order(ctx, change_order_id)
        updated = self.change_orders.decide(
            order,
            decision,
            str(payload["decision_date"]),
            str(payload.get("decided_by", ctx.principal_id)),
            str(payload.get("reason", "")),
        )
        record = self._tenant_record(
            ctx,
            "renovation_change_orders",
            change_order_id,
            "change order",
        )
        record["artifact"] = updated.as_dict()
        self.persistence.put("renovation_change_orders", change_order_id, record)
        approval = updated.approval_history[-1]
        self.persistence.put(
            "renovation_change_order_approvals",
            approval.approval_id,
            {
                "tenant_id": ctx.tenant_id,
                "organization_id": ctx.organization_id,
                "created_by": ctx.principal_id,
                "job_id": updated.job_id,
                "artifact": approval.as_dict(),
            },
        )
        event_type = CHANGE_ORDER_APPROVED if decision == "approved" else CHANGE_ORDER_REJECTED
        self.event_store.append(
            event_type,
            change_order_id,
            self._event_payload(
                ctx,
                job_id=updated.job_id,
                change_order_id=change_order_id,
                approval_id=approval.approval_id,
                status=updated.status,
                artifact_hash=_artifact_hash(updated.export_json()),
            ),
        )
        return updated

    def replay_change_order(self, ctx: TenantContext, change_order_id: str) -> ChangeOrder:
        value = self._tenant_record(
            ctx,
            "renovation_change_orders",
            change_order_id,
            "change order",
        )
        payload = dict(value["input"])
        job = self.get_job(ctx, str(payload["job_id"]))
        proposal = self.get_proposal(ctx, job.proposal_id)
        estimate_record = self._tenant_record(
            ctx,
            "renovation_estimates",
            proposal.estimate.estimate_id,
            "estimate",
        )
        replayed = self.change_orders.create(
            ctx.tenant_id,
            job.job_id,
            proposal.proposal_id,
            proposal.estimate,
            dict(estimate_record["input"]),
            payload,
        )
        approvals = [
            _change_order_approval_from_dict(dict(item["artifact"]))
            for item in self.persistence.list_tenant(
                "renovation_change_order_approvals",
                ctx.tenant_id,
            )
            if dict(item["artifact"]).get("change_order_id") == change_order_id
        ]
        for approval in sorted(approvals, key=lambda item: item.approval_id):
            replayed = self.change_orders.decide(
                replayed,
                approval.decision,
                approval.decision_date,
                approval.decided_by,
                approval.reason,
            )
        original = _change_order_from_dict(dict(value["artifact"]))
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation change order replay diverged")
        return replayed

    def export_change_order(
        self,
        ctx: TenantContext,
        change_order_id: str,
        export_format: str = "json",
    ) -> dict[str, object]:
        order = self.get_change_order(ctx, change_order_id)
        if export_format == "json":
            content = order.export_json()
        elif export_format == "text":
            content = order.rendered_text
        else:
            raise ValueError("change order export format must be json or text")
        export = {
            "tenant_id": ctx.tenant_id,
            "job_id": order.job_id,
            "change_order_id": change_order_id,
            "format": export_format,
            "content": content,
            "artifact_hash": _artifact_hash(content),
            "template_id": order.template_id,
            "template_version": order.template_version,
        }
        self.persistence.put(
            "renovation_change_order_exports",
            f"{change_order_id}:{export_format}",
            export,
        )
        self.event_store.append(
            CHANGE_ORDER_EXPORTED,
            change_order_id,
            self._event_payload(
                ctx,
                job_id=order.job_id,
                change_order_id=change_order_id,
                format=export_format,
                artifact_hash=export["artifact_hash"],
            ),
        )
        return export

    def create_schedule(self, ctx: TenantContext, payload: dict[str, object]) -> Schedule:
        job = self.get_job(ctx, str(payload["job_id"]))
        schedule = self.scheduling.create(ctx.tenant_id, job, payload)
        self.persistence.put(
            "renovation_schedules",
            schedule.schedule_id,
            {
                **self._record(ctx, payload, schedule.as_dict()),
                "job_id": job.job_id,
            },
        )
        self.event_store.append(
            SCHEDULE_CREATED,
            schedule.schedule_id,
            self._event_payload(
                ctx,
                job_id=job.job_id,
                schedule_id=schedule.schedule_id,
                schedule_hash=schedule.schedule_hash,
            ),
        )
        return schedule

    def get_schedule(self, ctx: TenantContext, schedule_id: str) -> Schedule:
        value = self._tenant_record(
            ctx,
            "renovation_schedules",
            schedule_id,
            "schedule",
        )
        return _schedule_from_dict(dict(value["artifact"]))

    def replay_schedule(self, ctx: TenantContext, schedule_id: str) -> Schedule:
        value = self._tenant_record(
            ctx,
            "renovation_schedules",
            schedule_id,
            "schedule",
        )
        payload = dict(value["input"])
        job = self.get_job(ctx, str(payload["job_id"]))
        replayed = self.scheduling.create(ctx.tenant_id, job, payload)
        evidence = sorted(
            (
                item
                for item in self.persistence.list_tenant(
                    "renovation_schedule_recalculations",
                    ctx.tenant_id,
                )
                if item.get("schedule_id") == schedule_id
            ),
            key=lambda item: int(item["revision"]),
        )
        for item in evidence:
            replayed = self.scheduling.recalculate(
                replayed,
                tuple(
                    _crew_assignment_from_dict(dict(record))
                    for record in item["assignments"]
                ),
                tuple(
                    _crew_availability_from_dict(dict(record))
                    for record in item["availability"]
                ),
                tuple(
                    _material_delivery_from_dict(dict(record))
                    for record in item["deliveries"]
                ),
                dict(item["input"]),
            )
        original = _schedule_from_dict(dict(value["artifact"]))
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation schedule replay diverged")
        return replayed

    def recalculate_schedule(
        self,
        ctx: TenantContext,
        schedule_id: str,
        payload: dict[str, object],
    ) -> Schedule:
        schedule = self.get_schedule(ctx, schedule_id)
        assignments = tuple(
            _crew_assignment_from_dict(dict(item["artifact"]))
            for item in self.persistence.list_tenant(
                "renovation_crew_assignments",
                ctx.tenant_id,
            )
            if dict(item["artifact"]).get("status") != "cancelled"
        )
        availability = tuple(
            _crew_availability_from_dict(dict(item["artifact"]))
            for item in self.persistence.list_tenant(
                "renovation_crew_availability",
                ctx.tenant_id,
            )
        )
        deliveries = tuple(
            _material_delivery_from_dict(dict(item["artifact"]))
            for item in self.persistence.list_tenant(
                "renovation_material_deliveries",
                ctx.tenant_id,
            )
            if dict(item["artifact"]).get("schedule_id") == schedule_id
        )
        recalculated = self.scheduling.recalculate(
            schedule,
            assignments,
            availability,
            deliveries,
            payload,
        )
        record = self._tenant_record(
            ctx,
            "renovation_schedules",
            schedule_id,
            "schedule",
        )
        record["artifact"] = recalculated.as_dict()
        self.persistence.put("renovation_schedules", schedule_id, record)
        evidence = {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": ctx.principal_id,
            "schedule_id": schedule_id,
            "revision": recalculated.revision,
            "input": payload,
            "assignments": [item.as_dict() for item in assignments],
            "availability": [item.as_dict() for item in availability],
            "deliveries": [item.as_dict() for item in deliveries],
            "schedule_hash": recalculated.schedule_hash,
        }
        self.persistence.put(
            "renovation_schedule_recalculations",
            f"{schedule_id}:{recalculated.revision:06d}",
            evidence,
        )
        for impact in recalculated.delay_impacts:
            self.persistence.put(
                "renovation_delay_impacts",
                impact.delay_id,
                {
                    "tenant_id": ctx.tenant_id,
                    "organization_id": ctx.organization_id,
                    "created_by": ctx.principal_id,
                    "job_id": recalculated.job_id,
                    "artifact": impact.as_dict(),
                },
            )
            self.event_store.append(
                DELAY_DETECTED,
                impact.delay_id,
                self._event_payload(
                    ctx,
                    job_id=recalculated.job_id,
                    schedule_id=schedule_id,
                    delay_id=impact.delay_id,
                    delay_days=impact.delay_days,
                ),
            )
        self.event_store.append(
            SCHEDULE_RECALCULATED,
            schedule_id,
            self._event_payload(
                ctx,
                job_id=recalculated.job_id,
                schedule_id=schedule_id,
                revision=recalculated.revision,
                projected_completion_date=recalculated.projected_completion_date,
                schedule_hash=recalculated.schedule_hash,
            ),
        )
        self.event_store.append(
            SCHEDULE_UPDATED,
            schedule_id,
            self._event_payload(
                ctx,
                job_id=recalculated.job_id,
                schedule_id=schedule_id,
                update_type="recalculation",
            ),
        )
        return recalculated

    def schedule_summary(self, ctx: TenantContext, job_id: str) -> dict[str, object]:
        self.get_job(ctx, job_id)
        schedules = [
            _schedule_from_dict(dict(item["artifact"]))
            for item in self.persistence.list_tenant(
                "renovation_schedules",
                ctx.tenant_id,
            )
            if dict(item["artifact"]).get("job_id") == job_id
        ]
        if not schedules:
            raise NotFoundError("renovation schedule not found")
        schedule = sorted(
            schedules,
            key=lambda item: (item.revision, item.schedule_id),
        )[-1]
        summary = self.scheduling.customer_summary(schedule)
        self.persistence.put(
            "renovation_schedule_summaries",
            f"{schedule.schedule_id}:{schedule.revision:06d}",
            {
                "tenant_id": ctx.tenant_id,
                "organization_id": ctx.organization_id,
                "created_by": ctx.principal_id,
                "job_id": job_id,
                **summary,
            },
        )
        return summary

    def create_crew(self, ctx: TenantContext, payload: dict[str, object]) -> Crew:
        crew = self.crews.create(ctx.tenant_id, payload)
        self.persistence.put(
            "renovation_crews",
            crew.crew_id,
            self._record(ctx, payload, crew.as_dict()),
        )
        self.event_store.append(
            CREW_CREATED,
            crew.crew_id,
            self._event_payload(
                ctx,
                crew_id=crew.crew_id,
                artifact_hash=_artifact_hash(crew.export_json()),
            ),
        )
        return crew

    def get_crew(self, ctx: TenantContext, crew_id: str) -> Crew:
        value = self._tenant_record(ctx, "renovation_crews", crew_id, "crew")
        return _crew_from_dict(dict(value["artifact"]))

    def update_crew_availability(
        self,
        ctx: TenantContext,
        crew_id: str,
        payload: dict[str, object],
    ) -> CrewAvailability:
        self.get_crew(ctx, crew_id)
        availability = self.crews.availability(ctx.tenant_id, crew_id, payload)
        self.persistence.put(
            "renovation_crew_availability",
            availability.availability_id,
            self._record(ctx, payload, availability.as_dict()),
        )
        self.event_store.append(
            CREW_AVAILABILITY_UPDATED,
            availability.availability_id,
            self._event_payload(
                ctx,
                crew_id=crew_id,
                availability_id=availability.availability_id,
                status=availability.status,
            ),
        )
        return availability

    def create_crew_assignment(
        self,
        ctx: TenantContext,
        payload: dict[str, object],
    ) -> CrewAssignment:
        crew = self.get_crew(ctx, str(payload["crew_id"]))
        schedule = self.get_schedule(ctx, str(payload["schedule_id"]))
        if str(payload.get("job_id", schedule.job_id)) != schedule.job_id:
            raise AuthorizationError("crew assignment job does not match schedule")
        phase_id = str(payload["phase_id"])
        phase = next(
            (item for item in schedule.phases if item.phase_id == phase_id),
            None,
        )
        if phase is None:
            raise NotFoundError("renovation schedule phase not found")
        assignment = self.crews.assignment(
            ctx.tenant_id,
            crew.crew_id,
            schedule.job_id,
            schedule.schedule_id,
            phase_id,
            str(payload.get("start_date", phase.planned_start)),
            str(payload.get("end_date", phase.planned_end)),
            payload,
        )
        self.persistence.put(
            "renovation_crew_assignments",
            assignment.assignment_id,
            {
                **self._record(ctx, payload, assignment.as_dict()),
                "job_id": schedule.job_id,
                "schedule_id": schedule.schedule_id,
            },
        )
        self.event_store.append(
            CREW_ASSIGNED,
            assignment.assignment_id,
            self._event_payload(
                ctx,
                job_id=schedule.job_id,
                schedule_id=schedule.schedule_id,
                phase_id=phase_id,
                crew_id=crew.crew_id,
                assignment_id=assignment.assignment_id,
            ),
        )
        return assignment

    def unassign_crew(
        self,
        ctx: TenantContext,
        assignment_id: str,
    ) -> CrewAssignment:
        record = self._tenant_record(
            ctx,
            "renovation_crew_assignments",
            assignment_id,
            "crew assignment",
        )
        assignment = self.crews.unassign(
            _crew_assignment_from_dict(dict(record["artifact"]))
        )
        record["artifact"] = assignment.as_dict()
        self.persistence.put("renovation_crew_assignments", assignment_id, record)
        self.event_store.append(
            CREW_UNASSIGNED,
            assignment_id,
            self._event_payload(
                ctx,
                job_id=assignment.job_id,
                schedule_id=assignment.schedule_id,
                phase_id=assignment.phase_id,
                crew_id=assignment.crew_id,
                assignment_id=assignment_id,
            ),
        )
        return assignment

    def create_material_delivery(
        self,
        ctx: TenantContext,
        payload: dict[str, object],
    ) -> MaterialDelivery:
        schedule = self.get_schedule(ctx, str(payload["schedule_id"]))
        if str(payload.get("job_id", schedule.job_id)) != schedule.job_id:
            raise AuthorizationError("material delivery job does not match schedule")
        phase_id = str(payload["phase_id"])
        if phase_id not in {item.phase_id for item in schedule.phases}:
            raise NotFoundError("renovation schedule phase not found")
        delivery = self.deliveries.create(
            ctx.tenant_id,
            schedule.job_id,
            schedule.schedule_id,
            phase_id,
            payload,
        )
        self.persistence.put(
            "renovation_material_deliveries",
            delivery.delivery_id,
            {
                **self._record(ctx, payload, delivery.as_dict()),
                "job_id": schedule.job_id,
                "schedule_id": schedule.schedule_id,
            },
        )
        self.event_store.append(
            MATERIAL_DELIVERY_CREATED,
            delivery.delivery_id,
            self._event_payload(
                ctx,
                job_id=schedule.job_id,
                schedule_id=schedule.schedule_id,
                phase_id=phase_id,
                delivery_id=delivery.delivery_id,
                status=delivery.status,
            ),
        )
        return delivery

    def update_material_delivery(
        self,
        ctx: TenantContext,
        delivery_id: str,
        payload: dict[str, object],
    ) -> MaterialDelivery:
        record = self._tenant_record(
            ctx,
            "renovation_material_deliveries",
            delivery_id,
            "material delivery",
        )
        current = _material_delivery_from_dict(dict(record["artifact"]))
        updated = self.deliveries.update(current, payload)
        record["artifact"] = updated.as_dict()
        record["last_update"] = payload
        self.persistence.put("renovation_material_deliveries", delivery_id, record)
        self.event_store.append(
            MATERIAL_DELIVERY_UPDATED,
            delivery_id,
            self._event_payload(
                ctx,
                job_id=updated.job_id,
                schedule_id=updated.schedule_id,
                delivery_id=delivery_id,
                status=updated.status,
            ),
        )
        return updated

    def record_job_cost(
        self,
        ctx: TenantContext,
        job_id: str,
        payload: dict[str, object],
    ) -> JobCostRecord:
        self.get_job(ctx, job_id)
        cost = self.finance.record_cost(ctx.tenant_id, job_id, payload)
        self.persistence.put(
            "renovation_job_costs",
            cost.cost_record_id,
            {
                **self._record(ctx, payload, cost.as_dict()),
                "job_id": job_id,
            },
        )
        self.event_store.append(
            JOB_COST_RECORDED,
            cost.cost_record_id,
            self._event_payload(
                ctx,
                job_id=job_id,
                cost_record_id=cost.cost_record_id,
                category=cost.category,
                amount=cost.amount,
                financial_hash=_artifact_hash(cost.export_json()),
            ),
        )
        return cost

    def replay_job_cost(
        self,
        ctx: TenantContext,
        cost_record_id: str,
    ) -> JobCostRecord:
        record = self._tenant_record(
            ctx,
            "renovation_job_costs",
            cost_record_id,
            "job cost",
        )
        original = _job_cost_from_dict(dict(record["artifact"]))
        replayed = self.finance.record_cost(
            ctx.tenant_id,
            original.job_id,
            dict(record["input"]),
        )
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation job cost replay diverged")
        return replayed

    def job_profitability(
        self,
        ctx: TenantContext,
        job_id: str,
    ) -> ProfitabilityScorecard:
        job = self.get_job(ctx, job_id)
        proposal = self.get_proposal(ctx, job.proposal_id)
        approved_change_orders = tuple(
            _change_order_from_dict(dict(item["artifact"]))
            for item in self.persistence.list_tenant(
                "renovation_change_orders",
                ctx.tenant_id,
            )
            if dict(item["artifact"]).get("job_id") == job_id
            and dict(item["artifact"]).get("status") == "approved"
        )
        costs = tuple(
            _job_cost_from_dict(dict(item["artifact"]))
            for item in self.persistence.list_tenant(
                "renovation_job_costs",
                ctx.tenant_id,
            )
            if dict(item["artifact"]).get("job_id") == job_id
        )
        contracted_revenue = round(
            proposal.estimate.total
            + sum(item.total_adjustment for item in approved_change_orders),
            2,
        )
        estimated_cost = round(
            proposal.estimate.subtotal + proposal.estimate.contingency,
            2,
        )
        scorecard = self.profitability.scorecard(
            ctx.tenant_id,
            job_id,
            contracted_revenue,
            estimated_cost,
            costs,
        )
        evidence = {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": ctx.principal_id,
            "job_id": job_id,
            "contracted_revenue": contracted_revenue,
            "estimated_cost": estimated_cost,
            "costs": [item.as_dict() for item in costs],
            "approved_change_order_ids": sorted(
                item.change_order_id for item in approved_change_orders
            ),
            "artifact": scorecard.as_dict(),
        }
        self.persistence.put(
            "renovation_profitability_scorecards",
            scorecard.scorecard_id,
            evidence,
        )
        if scorecard.margin_variance:
            self.persistence.put(
                "renovation_margin_variances",
                scorecard.margin_variance.variance_id,
                {
                    "tenant_id": ctx.tenant_id,
                    "organization_id": ctx.organization_id,
                    "created_by": ctx.principal_id,
                    "job_id": job_id,
                    "artifact": scorecard.margin_variance.as_dict(),
                },
            )
            self.event_store.append(
                MARGIN_VARIANCE_DETECTED,
                scorecard.margin_variance.variance_id,
                self._event_payload(
                    ctx,
                    job_id=job_id,
                    variance_id=scorecard.margin_variance.variance_id,
                    variance_percentage_points=(
                        scorecard.margin_variance.variance_percentage_points
                    ),
                ),
            )
        if scorecard.cost_overrun_alert:
            self.persistence.put(
                "renovation_cost_overrun_alerts",
                scorecard.cost_overrun_alert.alert_id,
                {
                    "tenant_id": ctx.tenant_id,
                    "organization_id": ctx.organization_id,
                    "created_by": ctx.principal_id,
                    "job_id": job_id,
                    "artifact": scorecard.cost_overrun_alert.as_dict(),
                },
            )
            self.event_store.append(
                COST_OVERRUN_DETECTED,
                scorecard.cost_overrun_alert.alert_id,
                self._event_payload(
                    ctx,
                    job_id=job_id,
                    alert_id=scorecard.cost_overrun_alert.alert_id,
                    overrun_amount=scorecard.cost_overrun_alert.overrun_amount,
                ),
            )
        self.event_store.append(
            PROFITABILITY_SCORECARD_GENERATED,
            scorecard.scorecard_id,
            self._event_payload(
                ctx,
                job_id=job_id,
                scorecard_id=scorecard.scorecard_id,
                financial_hash=scorecard.financial_hash,
            ),
        )
        return scorecard

    def replay_profitability(
        self,
        ctx: TenantContext,
        scorecard_id: str,
    ) -> ProfitabilityScorecard:
        record = self._tenant_record(
            ctx,
            "renovation_profitability_scorecards",
            scorecard_id,
            "profitability scorecard",
        )
        replayed = self.profitability.scorecard(
            ctx.tenant_id,
            str(record["job_id"]),
            float(record["contracted_revenue"]),
            float(record["estimated_cost"]),
            tuple(
                _job_cost_from_dict(dict(item)) for item in record.get("costs", ())
            ),
        )
        original = _profitability_scorecard_from_dict(dict(record["artifact"]))
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation profitability replay diverged")
        return replayed

    def create_invoice(
        self,
        ctx: TenantContext,
        payload: dict[str, object],
    ) -> Invoice:
        job = self.get_job(ctx, str(payload["job_id"]))
        proposal = self.get_proposal(ctx, job.proposal_id)
        invoice = self.invoicing.create_invoice(
            ctx.tenant_id,
            job.job_id,
            proposal.customer.customer_id,
            payload,
        )
        self.persistence.put(
            "renovation_invoices",
            invoice.invoice_id,
            {
                **self._record(ctx, payload, invoice.as_dict()),
                "job_id": job.job_id,
            },
        )
        self.event_store.append(
            INVOICE_CREATED,
            invoice.invoice_id,
            self._event_payload(
                ctx,
                job_id=job.job_id,
                invoice_id=invoice.invoice_id,
                total=invoice.total,
                due_date=invoice.due_date,
            ),
        )
        return invoice

    def get_invoice(self, ctx: TenantContext, invoice_id: str) -> Invoice:
        record = self._tenant_record(
            ctx,
            "renovation_invoices",
            invoice_id,
            "invoice",
        )
        return _invoice_from_dict(dict(record["artifact"]))

    def pay_invoice(
        self,
        ctx: TenantContext,
        invoice_id: str,
        payload: dict[str, object],
    ) -> Invoice:
        invoice = self.get_invoice(ctx, invoice_id)
        updated = self.invoicing.apply_invoice_payment(invoice, payload)
        record = self._tenant_record(
            ctx,
            "renovation_invoices",
            invoice_id,
            "invoice",
        )
        record["artifact"] = updated.as_dict()
        self.persistence.put("renovation_invoices", invoice_id, record)
        payment = updated.payment_records[-1]
        self._persist_payment(ctx, updated.job_id, payment)
        self.event_store.append(
            INVOICE_PAID,
            invoice_id,
            self._event_payload(
                ctx,
                job_id=updated.job_id,
                invoice_id=invoice_id,
                payment_id=payment.payment_id,
                amount=payment.amount,
                outstanding_balance=updated.outstanding_balance,
            ),
        )
        return updated

    def replay_invoice(self, ctx: TenantContext, invoice_id: str) -> Invoice:
        record = self._tenant_record(
            ctx,
            "renovation_invoices",
            invoice_id,
            "invoice",
        )
        original = _invoice_from_dict(dict(record["artifact"]))
        replayed = self.invoicing.create_invoice(
            ctx.tenant_id,
            original.job_id,
            original.customer_id,
            dict(record["input"]),
        )
        for payment in original.payment_records:
            replayed = self.invoicing.apply_invoice_payment(
                replayed,
                {
                    "payment_date": payment.payment_date,
                    "amount": payment.amount,
                    "method": payment.method,
                    "reference": payment.reference,
                },
            )
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation invoice replay diverged")
        return replayed

    def create_payable(
        self,
        ctx: TenantContext,
        payload: dict[str, object],
    ) -> VendorPayable:
        job = self.get_job(ctx, str(payload["job_id"]))
        payable = self.invoicing.create_payable(ctx.tenant_id, job.job_id, payload)
        self.persistence.put(
            "renovation_payables",
            payable.payable_id,
            {
                **self._record(ctx, payload, payable.as_dict()),
                "job_id": job.job_id,
            },
        )
        self.event_store.append(
            PAYABLE_CREATED,
            payable.payable_id,
            self._event_payload(
                ctx,
                job_id=job.job_id,
                payable_id=payable.payable_id,
                amount=payable.amount,
                due_date=payable.due_date,
            ),
        )
        return payable

    def get_payable(self, ctx: TenantContext, payable_id: str) -> VendorPayable:
        record = self._tenant_record(
            ctx,
            "renovation_payables",
            payable_id,
            "payable",
        )
        return _vendor_payable_from_dict(dict(record["artifact"]))

    def pay_payable(
        self,
        ctx: TenantContext,
        payable_id: str,
        payload: dict[str, object],
    ) -> VendorPayable:
        payable = self.get_payable(ctx, payable_id)
        updated = self.invoicing.apply_payable_payment(payable, payload)
        record = self._tenant_record(
            ctx,
            "renovation_payables",
            payable_id,
            "payable",
        )
        record["artifact"] = updated.as_dict()
        self.persistence.put("renovation_payables", payable_id, record)
        payment = updated.payment_records[-1]
        self._persist_payment(ctx, updated.job_id, payment)
        self.event_store.append(
            PAYABLE_PAID,
            payable_id,
            self._event_payload(
                ctx,
                job_id=updated.job_id,
                payable_id=payable_id,
                payment_id=payment.payment_id,
                amount=payment.amount,
                outstanding_balance=updated.outstanding_balance,
            ),
        )
        return updated

    def replay_payable(
        self,
        ctx: TenantContext,
        payable_id: str,
    ) -> VendorPayable:
        record = self._tenant_record(
            ctx,
            "renovation_payables",
            payable_id,
            "payable",
        )
        original = _vendor_payable_from_dict(dict(record["artifact"]))
        replayed = self.invoicing.create_payable(
            ctx.tenant_id,
            original.job_id,
            dict(record["input"]),
        )
        for payment in original.payment_records:
            replayed = self.invoicing.apply_payable_payment(
                replayed,
                {
                    "payment_date": payment.payment_date,
                    "amount": payment.amount,
                    "method": payment.method,
                    "reference": payment.reference,
                },
            )
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation payable replay diverged")
        return replayed

    def cash_flow_forecast(
        self,
        ctx: TenantContext,
        as_of_date: str,
    ) -> CashFlowForecast:
        ctx.require()
        invoices = tuple(
            _invoice_from_dict(dict(item["artifact"]))
            for item in self.persistence.list_tenant(
                "renovation_invoices",
                ctx.tenant_id,
            )
        )
        payables = tuple(
            _vendor_payable_from_dict(dict(item["artifact"]))
            for item in self.persistence.list_tenant(
                "renovation_payables",
                ctx.tenant_id,
            )
        )
        forecast = self.profitability.forecast(
            ctx.tenant_id,
            as_of_date,
            invoices,
            payables,
        )
        self.persistence.put(
            "renovation_cash_flow_forecasts",
            forecast.forecast_id,
            {
                "tenant_id": ctx.tenant_id,
                "organization_id": ctx.organization_id,
                "created_by": ctx.principal_id,
                "as_of_date": as_of_date,
                "invoices": [item.as_dict() for item in invoices],
                "payables": [item.as_dict() for item in payables],
                "artifact": forecast.as_dict(),
            },
        )
        self.event_store.append(
            CASH_FLOW_FORECAST_GENERATED,
            forecast.forecast_id,
            self._event_payload(
                ctx,
                forecast_id=forecast.forecast_id,
                as_of_date=forecast.as_of_date,
                forecast_hash=forecast.forecast_hash,
            ),
        )
        return forecast

    def replay_cash_flow(
        self,
        ctx: TenantContext,
        forecast_id: str,
    ) -> CashFlowForecast:
        record = self._tenant_record(
            ctx,
            "renovation_cash_flow_forecasts",
            forecast_id,
            "cash flow forecast",
        )
        replayed = self.profitability.forecast(
            ctx.tenant_id,
            str(record["as_of_date"]),
            tuple(_invoice_from_dict(dict(item)) for item in record["invoices"]),
            tuple(
                _vendor_payable_from_dict(dict(item)) for item in record["payables"]
            ),
        )
        original = _cash_flow_forecast_from_dict(dict(record["artifact"]))
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation cash flow replay diverged")
        return replayed

    def owner_financial_summary(
        self,
        ctx: TenantContext,
        as_of_date: str,
    ) -> dict[str, object]:
        jobs = tuple(
            _job_from_dict(dict(item["artifact"]))
            for item in self.persistence.list_tenant(
                "renovation_jobs",
                ctx.tenant_id,
            )
        )
        scorecards = tuple(
            self.job_profitability(ctx, item.job_id)
            for item in sorted(jobs, key=lambda value: value.job_id)
        )
        forecast = self.cash_flow_forecast(ctx, as_of_date)
        invoices = tuple(
            _invoice_from_dict(dict(item["artifact"]))
            for item in self.persistence.list_tenant(
                "renovation_invoices",
                ctx.tenant_id,
            )
        )
        payables = tuple(
            _vendor_payable_from_dict(dict(item["artifact"]))
            for item in self.persistence.list_tenant(
                "renovation_payables",
                ctx.tenant_id,
            )
        )
        summary = {
            "tenant_id": ctx.tenant_id,
            "as_of_date": as_of_date,
            "job_count": len(jobs),
            "contracted_revenue": round(
                sum(item.contracted_revenue for item in scorecards),
                2,
            ),
            "actual_cost": round(sum(item.actual_cost for item in scorecards), 2),
            "gross_profit": round(
                sum(item.actual_gross_profit for item in scorecards),
                2,
            ),
            "outstanding_receivables": round(
                sum(item.outstanding_balance for item in invoices),
                2,
            ),
            "outstanding_payables": round(
                sum(item.outstanding_balance for item in payables),
                2,
            ),
            "at_risk_jobs": sorted(
                item.job_id
                for item in scorecards
                if item.cost_overrun_alert or item.margin_variance
            ),
            "profitability_scorecards": [item.as_dict() for item in scorecards],
            "cash_flow_forecast": forecast.as_dict(),
        }
        summary["financial_hash"] = _artifact_hash(_canonical(summary))
        self.persistence.put(
            "renovation_owner_summaries",
            f"{ctx.tenant_id}:{as_of_date}",
            {
                "tenant_id": ctx.tenant_id,
                "organization_id": ctx.organization_id,
                "created_by": ctx.principal_id,
                **summary,
            },
        )
        return summary

    def _persist_payment(
        self,
        ctx: TenantContext,
        job_id: str,
        payment: PaymentRecord,
    ) -> None:
        self.persistence.put(
            "renovation_payments",
            payment.payment_id,
            {
                "tenant_id": ctx.tenant_id,
                "organization_id": ctx.organization_id,
                "created_by": ctx.principal_id,
                "job_id": job_id,
                "artifact": payment.as_dict(),
            },
        )

    def create_lead(self, ctx: TenantContext, payload: dict[str, object]) -> Lead:
        lead = self.leads.create(ctx.tenant_id, payload)
        self.persistence.put(
            "renovation_leads",
            lead.lead_id,
            self._record(ctx, payload, lead.as_dict()),
        )
        self.event_store.append(
            LEAD_CREATED,
            lead.lead_id,
            self._event_payload(
                ctx,
                lead_id=lead.lead_id,
                status=lead.status,
                source_type=lead.source.source_type,
                artifact_hash=_artifact_hash(lead.export_json()),
            ),
        )
        return lead

    def get_lead(self, ctx: TenantContext, lead_id: str) -> Lead:
        record = self._tenant_record(ctx, "renovation_leads", lead_id, "lead")
        return _lead_from_dict(dict(record["artifact"]))

    def update_lead(
        self,
        ctx: TenantContext,
        lead_id: str,
        payload: dict[str, object],
    ) -> Lead:
        lead = self.get_lead(ctx, lead_id)
        updated = self.leads.update(lead, payload)
        record = self._tenant_record(ctx, "renovation_leads", lead_id, "lead")
        record["artifact"] = updated.as_dict()
        record.setdefault("updates", []).append(payload)
        self.persistence.put("renovation_leads", lead_id, record)
        self.event_store.append(
            LEAD_UPDATED,
            lead_id,
            self._event_payload(
                ctx,
                lead_id=lead_id,
                previous_status=lead.status,
                status=updated.status,
                artifact_hash=_artifact_hash(updated.export_json()),
            ),
        )
        return updated

    def replay_lead(self, ctx: TenantContext, lead_id: str) -> Lead:
        record = self._tenant_record(ctx, "renovation_leads", lead_id, "lead")
        replayed = self.leads.create(ctx.tenant_id, dict(record["input"]))
        for update in record.get("updates", ()):
            replayed = self.leads.update(replayed, dict(update))
        if "conversion" in record:
            replayed = self.leads.convert(
                replayed,
                str(dict(record["artifact"])["customer_id"]),
            )
        original = _lead_from_dict(dict(record["artifact"]))
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation lead replay diverged")
        return replayed

    def convert_lead(
        self,
        ctx: TenantContext,
        lead_id: str,
        payload: dict[str, object],
    ) -> Customer:
        lead = self.get_lead(ctx, lead_id)
        customer_identity = {
            "tenant_id": ctx.tenant_id,
            "lead_id": lead_id,
            "name": str(payload.get("name", lead.name)),
            "email": str(payload.get("email", lead.email)),
            "phone": str(payload.get("phone", lead.phone)),
            "address": str(payload.get("address", lead.property_address)),
        }
        customer = Customer(
            customer_id=f"customer-{_artifact_hash(_canonical(customer_identity))[:20]}",
            name=customer_identity["name"],
            email=customer_identity["email"],
            phone=customer_identity["phone"],
            address=customer_identity["address"],
        )
        updated = self.leads.convert(lead, customer.customer_id)
        lead_record = self._tenant_record(ctx, "renovation_leads", lead_id, "lead")
        lead_record["artifact"] = updated.as_dict()
        lead_record["conversion"] = payload
        self.persistence.put("renovation_leads", lead_id, lead_record)
        self.persistence.put(
            "renovation_customers",
            customer.customer_id,
            {
                "tenant_id": ctx.tenant_id,
                "organization_id": ctx.organization_id,
                "created_by": ctx.principal_id,
                "lead_id": lead_id,
                "artifact": customer.as_dict(),
            },
        )
        self.event_store.append(
            LEAD_CONVERTED,
            lead_id,
            self._event_payload(
                ctx,
                lead_id=lead_id,
                customer_id=customer.customer_id,
            ),
        )
        return customer

    def create_opportunity(
        self,
        ctx: TenantContext,
        payload: dict[str, object],
    ) -> Opportunity:
        self._validate_crm_target(ctx, payload)
        opportunity = self.crm.opportunity(ctx.tenant_id, payload)
        self.persistence.put(
            "renovation_opportunities",
            opportunity.opportunity_id,
            self._record(ctx, payload, opportunity.as_dict()),
        )
        self.event_store.append(
            OPPORTUNITY_CREATED,
            opportunity.opportunity_id,
            self._event_payload(
                ctx,
                opportunity_id=opportunity.opportunity_id,
                lead_id=opportunity.lead_id,
                customer_id=opportunity.customer_id,
                stage=opportunity.stage,
            ),
        )
        return opportunity

    def get_opportunity(
        self,
        ctx: TenantContext,
        opportunity_id: str,
    ) -> Opportunity:
        record = self._tenant_record(
            ctx,
            "renovation_opportunities",
            opportunity_id,
            "opportunity",
        )
        return _opportunity_from_dict(dict(record["artifact"]))

    def update_opportunity_stage(
        self,
        ctx: TenantContext,
        opportunity_id: str,
        stage: str,
    ) -> Opportunity:
        current = self.get_opportunity(ctx, opportunity_id)
        updated = self.crm.update_stage(current, stage)
        record = self._tenant_record(
            ctx,
            "renovation_opportunities",
            opportunity_id,
            "opportunity",
        )
        record["artifact"] = updated.as_dict()
        record.setdefault("stage_updates", []).append(stage)
        self.persistence.put("renovation_opportunities", opportunity_id, record)
        self.event_store.append(
            OPPORTUNITY_STAGE_CHANGED,
            opportunity_id,
            self._event_payload(
                ctx,
                opportunity_id=opportunity_id,
                previous_stage=current.stage,
                stage=updated.stage,
            ),
        )
        return updated

    def replay_opportunity(
        self,
        ctx: TenantContext,
        opportunity_id: str,
    ) -> Opportunity:
        record = self._tenant_record(
            ctx,
            "renovation_opportunities",
            opportunity_id,
            "opportunity",
        )
        replayed = self.crm.opportunity(ctx.tenant_id, dict(record["input"]))
        for stage in record.get("stage_updates", ()):
            replayed = self.crm.update_stage(replayed, str(stage))
        original = _opportunity_from_dict(dict(record["artifact"]))
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation opportunity replay diverged")
        return replayed

    def create_follow_up(
        self,
        ctx: TenantContext,
        payload: dict[str, object],
    ) -> FollowUpTask:
        if payload.get("lead_id"):
            self.get_lead(ctx, str(payload["lead_id"]))
        if payload.get("opportunity_id"):
            self.get_opportunity(ctx, str(payload["opportunity_id"]))
        follow_up = self.crm.follow_up(ctx.tenant_id, payload)
        self.persistence.put(
            "renovation_follow_ups",
            follow_up.follow_up_id,
            self._record(ctx, payload, follow_up.as_dict()),
        )
        self.event_store.append(
            FOLLOW_UP_TASK_CREATED,
            follow_up.follow_up_id,
            self._event_payload(
                ctx,
                follow_up_id=follow_up.follow_up_id,
                lead_id=follow_up.lead_id,
                opportunity_id=follow_up.opportunity_id,
                due_date=follow_up.due_date,
            ),
        )
        return follow_up

    def create_appointment(
        self,
        ctx: TenantContext,
        payload: dict[str, object],
    ) -> AppointmentRequest:
        self._validate_crm_target(ctx, payload)
        appointment = self.crm.appointment(ctx.tenant_id, payload)
        self.persistence.put(
            "renovation_appointments",
            appointment.appointment_id,
            self._record(ctx, payload, appointment.as_dict()),
        )
        self.event_store.append(
            APPOINTMENT_REQUESTED,
            appointment.appointment_id,
            self._event_payload(
                ctx,
                appointment_id=appointment.appointment_id,
                lead_id=appointment.lead_id,
                customer_id=appointment.customer_id,
                requested_date=appointment.requested_date,
            ),
        )
        return appointment

    def create_site_visit(
        self,
        ctx: TenantContext,
        payload: dict[str, object],
    ) -> SiteVisit:
        record = self._tenant_record(
            ctx,
            "renovation_appointments",
            str(payload["appointment_id"]),
            "appointment",
        )
        appointment = _appointment_from_dict(dict(record["artifact"]))
        visit = self.crm.site_visit(ctx.tenant_id, appointment, payload)
        self.persistence.put(
            "renovation_site_visits",
            visit.site_visit_id,
            self._record(ctx, payload, visit.as_dict()),
        )
        self.event_store.append(
            SITE_VISIT_RECORDED,
            visit.site_visit_id,
            self._event_payload(
                ctx,
                site_visit_id=visit.site_visit_id,
                appointment_id=visit.appointment_id,
                lead_id=visit.lead_id,
                customer_id=visit.customer_id,
            ),
        )
        return visit

    def record_customer_message(
        self,
        ctx: TenantContext,
        payload: dict[str, object],
    ) -> CustomerMessage:
        customer_id = str(payload["customer_id"])
        self._customer_record(ctx, customer_id)
        job_id = str(payload.get("job_id", ""))
        if job_id and self._job_customer_id(ctx, job_id) != customer_id:
            raise AuthorizationError("customer message job belongs to another customer")
        message, communication = self.communications.message(ctx.tenant_id, payload)
        self.persistence.put(
            "renovation_customer_messages",
            message.message_id,
            self._record(ctx, payload, message.as_dict()),
        )
        self.persistence.put(
            "renovation_communications",
            communication.communication_id,
            self._record(ctx, payload, communication.as_dict()),
        )
        self.event_store.append(
            CUSTOMER_MESSAGE_RECORDED,
            message.message_id,
            self._event_payload(
                ctx,
                customer_id=customer_id,
                job_id=job_id,
                message_id=message.message_id,
                communication_id=communication.communication_id,
                channel=message.channel,
            ),
        )
        return message

    def customer_portal_view(
        self,
        ctx: TenantContext,
        customer_id: str,
        generated_date: str,
    ) -> CustomerPortalView:
        self._customer_record(ctx, customer_id)
        projects = tuple(
            self._customer_project_projection(ctx, job)
            for job in sorted(
                (
                    _job_from_dict(dict(item["artifact"]))
                    for item in self.persistence.list_tenant(
                        "renovation_jobs",
                        ctx.tenant_id,
                    )
                    if self._job_customer_id(
                        ctx,
                        str(dict(item["artifact"])["job_id"]),
                    )
                    == customer_id
                ),
                key=lambda item: item.job_id,
            )
        )
        communications = tuple(
            {
                "message_id": message.message_id,
                "job_id": message.job_id,
                "channel": message.channel,
                "direction": message.direction,
                "message_date": message.message_date,
                "subject": message.subject,
                "body": message.body,
            }
            for message in sorted(
                (
                    _customer_message_from_dict(dict(item["artifact"]))
                    for item in self.persistence.list_tenant(
                        "renovation_customer_messages",
                        ctx.tenant_id,
                    )
                    if dict(item["artifact"]).get("customer_id") == customer_id
                    and dict(item["artifact"]).get("visibility") == "customer"
                ),
                key=lambda item: (item.message_date, item.message_id),
            )
        )
        view = self.customer_portal.view(
            ctx.tenant_id,
            customer_id,
            generated_date,
            projects,
            communications,
        )
        self.persistence.put(
            "renovation_portal_views",
            view.portal_view_id,
            {
                "tenant_id": ctx.tenant_id,
                "organization_id": ctx.organization_id,
                "created_by": ctx.principal_id,
                "customer_id": customer_id,
                "generated_date": generated_date,
                "policy": DEFAULT_VISIBILITY_POLICY.as_dict(),
                "projects": list(projects),
                "communications": list(communications),
                "artifact": view.as_dict(),
            },
        )
        self.event_store.append(
            CUSTOMER_PORTAL_VIEW_GENERATED,
            view.portal_view_id,
            self._event_payload(
                ctx,
                customer_id=customer_id,
                portal_view_id=view.portal_view_id,
                policy_id=view.policy_id,
                view_hash=view.view_hash,
            ),
        )
        return view

    def replay_customer_portal_view(
        self,
        ctx: TenantContext,
        portal_view_id: str,
    ) -> CustomerPortalView:
        record = self._tenant_record(
            ctx,
            "renovation_portal_views",
            portal_view_id,
            "customer portal view",
        )
        replayed = self.customer_portal.view(
            ctx.tenant_id,
            str(record["customer_id"]),
            str(record["generated_date"]),
            tuple(dict(item) for item in record["projects"]),
            tuple(dict(item) for item in record["communications"]),
            _visibility_policy_from_dict(dict(record["policy"])),
        )
        original = _portal_view_from_dict(dict(record["artifact"]))
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation customer portal replay diverged")
        return replayed

    def customer_job_status(
        self,
        ctx: TenantContext,
        job_id: str,
        generated_date: str,
    ) -> dict[str, object]:
        customer_id = self._job_customer_id(ctx, job_id)
        view = self.customer_portal_view(ctx, customer_id, generated_date)
        project = next(
            (item for item in view.projects if item["job_id"] == job_id),
            None,
        )
        if project is None:
            raise NotFoundError("renovation customer job status not found")
        return {
            "customer_id": customer_id,
            "generated_date": generated_date,
            "policy_id": view.policy_id,
            "project": project,
        }

    def _customer_project_projection(
        self,
        ctx: TenantContext,
        job: Job,
    ) -> dict[str, object]:
        proposal = self.get_proposal(ctx, job.proposal_id)
        schedule_records = [
            _schedule_from_dict(dict(item["artifact"]))
            for item in self.persistence.list_tenant(
                "renovation_schedules",
                ctx.tenant_id,
            )
            if dict(item["artifact"]).get("job_id") == job.job_id
        ]
        schedule = (
            sorted(schedule_records, key=lambda item: (item.revision, item.schedule_id))[-1]
            if schedule_records
            else None
        )
        daily_logs = [
            item
            for item in self.persistence.list_tenant(
                "renovation_daily_logs",
                ctx.tenant_id,
            )
            if dict(item["artifact"]).get("job_id") == job.job_id
            and not bool(dict(item.get("input", {})).get("internal", False))
            and dict(item.get("input", {})).get("visibility", "customer") != "internal"
        ]
        photos = [
            _photo_from_dict(dict(item["artifact"]))
            for item in self.persistence.list_tenant(
                "renovation_photo_records",
                ctx.tenant_id,
            )
            if dict(item["artifact"]).get("job_id") == job.job_id
            and bool(
                dict(item.get("input", {})).get(
                    "approved_for_customer",
                    dict(item.get("input", {})).get("customer_visible", False),
                )
            )
        ]
        change_orders = [
            _change_order_from_dict(dict(item["artifact"]))
            for item in self.persistence.list_tenant(
                "renovation_change_orders",
                ctx.tenant_id,
            )
            if dict(item["artifact"]).get("job_id") == job.job_id
            and dict(item["artifact"]).get("status") == "approved"
        ]
        invoices = [
            _invoice_from_dict(dict(item["artifact"]))
            for item in self.persistence.list_tenant(
                "renovation_invoices",
                ctx.tenant_id,
            )
            if dict(item["artifact"]).get("job_id") == job.job_id
        ]
        current_phase = next(
            (item.name for item in job.phases if item.phase_id == job.current_phase),
            "",
        )
        return {
            "job_id": job.job_id,
            "project_title": job.title,
            "project_status": job.status,
            "scope_summary": list(proposal.scope_of_work),
            "current_phase": current_phase,
            "approved_timeline": (
                {
                    "start_date": schedule.start_date,
                    "projected_completion_date": schedule.projected_completion_date,
                    "phases": [
                        {
                            "name": item.name,
                            "start_date": item.planned_start,
                            "end_date": item.planned_end,
                            "status": item.status,
                        }
                        for item in schedule.phases
                    ],
                }
                if schedule
                else None
            ),
            "recent_progress": [
                {
                    "work_date": str(dict(item["artifact"])["work_date"]),
                    "summary": str(dict(item["artifact"])["summary"]),
                    "completed_work": list(
                        dict(item["artifact"]).get("completed_work", ())
                    ),
                    "next_steps": list(dict(item["artifact"]).get("next_steps", ())),
                }
                for item in sorted(
                    daily_logs,
                    key=lambda value: (
                        str(dict(value["artifact"])["work_date"]),
                        str(dict(value["artifact"])["daily_log_id"]),
                    ),
                    reverse=True,
                )[:5]
            ],
            "approved_photos": [
                {
                    "photo_record_id": item.photo_record_id,
                    "captured_date": item.captured_date,
                    "storage_reference": item.storage_reference,
                    "caption": item.caption,
                    "phase_id": item.phase_id,
                }
                for item in sorted(photos, key=lambda value: value.photo_record_id)
            ],
            "approved_change_orders": [
                {
                    "change_order_id": item.change_order_id,
                    "title": item.title,
                    "description": item.description,
                    "status": item.status,
                    "total_adjustment": item.total_adjustment,
                    "schedule_delta_days": item.schedule_delta_days,
                }
                for item in sorted(
                    change_orders,
                    key=lambda value: value.change_order_id,
                )
            ],
            "invoice_status": [
                {
                    "invoice_id": item.invoice_id,
                    "description": item.description,
                    "due_date": item.due_date,
                    "total": item.total,
                    "paid_amount": item.paid_amount,
                    "outstanding_balance": item.outstanding_balance,
                    "status": item.status,
                }
                for item in sorted(invoices, key=lambda value: value.invoice_id)
            ],
        }

    def _validate_crm_target(
        self,
        ctx: TenantContext,
        payload: dict[str, object],
    ) -> None:
        if payload.get("lead_id"):
            self.get_lead(ctx, str(payload["lead_id"]))
        if payload.get("customer_id"):
            self._customer_record(ctx, str(payload["customer_id"]))

    def _customer_record(
        self,
        ctx: TenantContext,
        customer_id: str,
    ) -> dict[str, object]:
        record = self.persistence.get("renovation_customers", customer_id)
        if record is not None:
            if record.get("tenant_id") != ctx.tenant_id:
                raise AuthorizationError("cross-tenant renovation customer access denied")
            return record
        for item in self.persistence.list("renovation_proposals"):
            customer = dict(dict(item["artifact"])["customer"])
            if customer.get("customer_id") == customer_id:
                if item.get("tenant_id") != ctx.tenant_id:
                    raise AuthorizationError(
                        "cross-tenant renovation customer access denied"
                    )
                return {
                    "tenant_id": ctx.tenant_id,
                    "artifact": customer,
                }
        raise NotFoundError("renovation customer not found")

    def _job_customer_id(self, ctx: TenantContext, job_id: str) -> str:
        job = self.get_job(ctx, job_id)
        return self.get_proposal(ctx, job.proposal_id).customer.customer_id

    def _persist_photo(
        self,
        ctx: TenantContext,
        job_id: str,
        payload: dict[str, object],
    ) -> PhotoRecord:
        photo = self.documentation.photo(ctx.tenant_id, job_id, payload)
        self.persistence.put(
            "renovation_photo_records",
            photo.photo_record_id,
            {
                **self._record(ctx, payload, photo.as_dict()),
                "job_id": job_id,
            },
        )
        self.event_store.append(
            PHOTO_RECORD_ADDED,
            photo.photo_record_id,
            self._event_payload(
                ctx,
                job_id=job_id,
                photo_record_id=photo.photo_record_id,
                metadata_hash=_artifact_hash(photo.export_json()),
            ),
        )
        return photo

    def _persist_issue(
        self,
        ctx: TenantContext,
        job_id: str,
        payload: dict[str, object],
    ) -> IssueRecord:
        issue = self.documentation.issue(ctx.tenant_id, job_id, payload)
        self.persistence.put(
            "renovation_issue_records",
            issue.issue_record_id,
            {
                **self._record(ctx, payload, issue.as_dict()),
                "job_id": job_id,
            },
        )
        self.event_store.append(
            ISSUE_RECORD_ADDED,
            issue.issue_record_id,
            self._event_payload(
                ctx,
                job_id=job_id,
                issue_record_id=issue.issue_record_id,
                artifact_hash=_artifact_hash(issue.export_json()),
            ),
        )
        return issue

    def _emit_job_documentation_update(
        self,
        ctx: TenantContext,
        job_id: str,
        record_type: str,
        record_id: str,
    ) -> None:
        self.event_store.append(
            JOB_UPDATED,
            job_id,
            self._event_payload(
                ctx,
                job_id=job_id,
                update_type=record_type,
                record_id=record_id,
            ),
        )

    def _job_artifacts(
        self,
        ctx: TenantContext,
        collection: str,
        job_id: str,
        date_field: str,
        date_value: str,
    ) -> list[dict[str, object]]:
        return [
            dict(item["artifact"])
            for item in self.persistence.list_tenant(collection, ctx.tenant_id)
            if dict(item.get("artifact", {})).get("job_id") == job_id
            and dict(item.get("artifact", {})).get(date_field) == date_value
        ]

    def _record(
        self,
        ctx: TenantContext,
        input_value: dict[str, object],
        artifact: dict[str, object],
    ) -> dict[str, object]:
        return {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": ctx.principal_id,
            "input": input_value,
            "artifact": artifact,
        }

    def _event_payload(self, ctx: TenantContext, **values: object) -> dict[str, object]:
        return {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            **values,
        }

    def _tenant_record(
        self,
        ctx: TenantContext,
        collection: str,
        key: str,
        label: str,
    ) -> dict[str, object]:
        ctx.require()
        value = self.persistence.get(collection, key)
        if value is None:
            raise NotFoundError(f"renovation {label} not found")
        if value.get("tenant_id") != ctx.tenant_id:
            raise AuthorizationError(f"cross-tenant renovation {label} access denied")
        return value


def _artifact_hash(value: str) -> str:
    from hashlib import sha256

    return sha256(value.encode()).hexdigest()


def _canonical(value: object) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _estimate_from_dict(value: dict[str, object]) -> Estimate:
    return Estimate(
        estimate_id=str(value["estimate_id"]),
        tenant_id=str(value["tenant_id"]),
        project_id=str(value["project_id"]),
        scope_description=str(value["scope_description"]),
        scope_items=tuple(ScopeItem(**item) for item in value["scope_items"]),
        material_lines=tuple(MaterialLine(**item) for item in value["material_lines"]),
        labor_lines=tuple(LaborLine(**item) for item in value["labor_lines"]),
        material_total=float(value["material_total"]),
        labor_total=float(value["labor_total"]),
        subtotal=float(value["subtotal"]),
        contingency_percentage=float(value["contingency_percentage"]),
        contingency=float(value["contingency"]),
        taxable_amount=float(value["taxable_amount"]),
        tax_percentage=float(value["tax_percentage"]),
        tax=float(value["tax"]),
        total=float(value["total"]),
        notes=str(value["notes"]),
        rate_table_version=str(value.get("rate_table_version", "renovation-rates-v1")),
    )


def _proposal_from_dict(value: dict[str, object]) -> Proposal:
    return Proposal(
        proposal_id=str(value["proposal_id"]),
        tenant_id=str(value["tenant_id"]),
        customer=Customer(**dict(value["customer"])),
        project=Project(**dict(value["project"])),
        estimate=_estimate_from_dict(dict(value["estimate"])),
        template_id=str(value["template_id"]),
        template_version=str(value["template_version"]),
        style=str(value["style"]),
        scope_of_work=tuple(str(item) for item in value["scope_of_work"]),
        payment_schedule=tuple(PaymentSchedule(**item) for item in value["payment_schedule"]),
        timeline=tuple(Timeline(**item) for item in value["timeline"]),
        warranty=str(value["warranty"]),
        terms_and_conditions=tuple(str(item) for item in value["terms_and_conditions"]),
        rendered_text=str(value["rendered_text"]),
    )


def _job_from_dict(value: dict[str, object]) -> Job:
    return Job(
        job_id=str(value["job_id"]),
        tenant_id=str(value["tenant_id"]),
        proposal_id=str(value["proposal_id"]),
        project_id=str(value["project_id"]),
        title=str(value["title"]),
        status=str(value["status"]),
        accepted_date=str(value["accepted_date"]),
        acceptance_reference=str(value["acceptance_reference"]),
        phases=tuple(JobPhase(**item) for item in value["phases"]),
        current_phase=str(value["current_phase"]),
        template_id=str(value["template_id"]),
    )


def _photo_from_dict(value: dict[str, object]) -> PhotoRecord:
    return PhotoRecord(
        photo_record_id=str(value["photo_record_id"]),
        tenant_id=str(value["tenant_id"]),
        job_id=str(value["job_id"]),
        captured_date=str(value["captured_date"]),
        file_name=str(value["file_name"]),
        storage_reference=str(value["storage_reference"]),
        sha256=str(value["sha256"]),
        caption=str(value.get("caption", "")),
        phase_id=str(value.get("phase_id", "")),
    )


def _issue_from_dict(value: dict[str, object]) -> IssueRecord:
    return IssueRecord(
        issue_record_id=str(value["issue_record_id"]),
        tenant_id=str(value["tenant_id"]),
        job_id=str(value["job_id"]),
        reported_date=str(value["reported_date"]),
        title=str(value["title"]),
        description=str(value["description"]),
        severity=str(value["severity"]),
        status=str(value["status"]),
        phase_id=str(value.get("phase_id", "")),
    )


def _daily_log_from_dict(value: dict[str, object]) -> DailyLog:
    return DailyLog(
        daily_log_id=str(value["daily_log_id"]),
        tenant_id=str(value["tenant_id"]),
        job_id=str(value["job_id"]),
        work_date=str(value["work_date"]),
        summary=str(value["summary"]),
        weather=str(value["weather"]),
        crew_hours=float(value["crew_hours"]),
        completed_work=tuple(str(item) for item in value["completed_work"]),
        next_steps=tuple(str(item) for item in value["next_steps"]),
        photo_record_ids=tuple(str(item) for item in value["photo_record_ids"]),
        issue_record_ids=tuple(str(item) for item in value["issue_record_ids"]),
    )


def _field_note_from_dict(value: dict[str, object]) -> FieldNote:
    return FieldNote(
        field_note_id=str(value["field_note_id"]),
        tenant_id=str(value["tenant_id"]),
        job_id=str(value["job_id"]),
        note_date=str(value["note_date"]),
        author=str(value["author"]),
        note=str(value["note"]),
        source=str(value["source"]),
        photo_record_ids=tuple(str(item) for item in value["photo_record_ids"]),
    )


def _change_order_approval_from_dict(value: dict[str, object]) -> ChangeOrderApproval:
    return ChangeOrderApproval(
        approval_id=str(value["approval_id"]),
        change_order_id=str(value["change_order_id"]),
        decision=str(value["decision"]),
        decision_date=str(value["decision_date"]),
        decided_by=str(value["decided_by"]),
        reason=str(value.get("reason", "")),
    )


def _change_order_from_dict(value: dict[str, object]) -> ChangeOrder:
    return ChangeOrder(
        change_order_id=str(value["change_order_id"]),
        tenant_id=str(value["tenant_id"]),
        job_id=str(value["job_id"]),
        proposal_id=str(value["proposal_id"]),
        source_type=str(value["source_type"]),
        source_reference=str(value["source_reference"]),
        title=str(value["title"]),
        description=str(value["description"]),
        status=str(value["status"]),
        lines=tuple(ChangeOrderLine(**item) for item in value["lines"]),
        material_total=float(value["material_total"]),
        labor_total=float(value["labor_total"]),
        subtotal=float(value["subtotal"]),
        contingency_percentage=float(value["contingency_percentage"]),
        contingency=float(value["contingency"]),
        tax_percentage=float(value["tax_percentage"]),
        tax=float(value["tax"]),
        total_adjustment=float(value["total_adjustment"]),
        schedule_delta_days=int(value["schedule_delta_days"]),
        template_id=str(value["template_id"]),
        template_version=str(value["template_version"]),
        approval_history=tuple(
            _change_order_approval_from_dict(dict(item))
            for item in value["approval_history"]
        ),
        rendered_text=str(value["rendered_text"]),
    )


def _crew_member_from_dict(value: dict[str, object]) -> CrewMember:
    return CrewMember(
        member_id=str(value["member_id"]),
        name=str(value["name"]),
        role=str(value["role"]),
        skills=tuple(str(item) for item in value.get("skills", ())),
    )


def _crew_from_dict(value: dict[str, object]) -> Crew:
    return Crew(
        crew_id=str(value["crew_id"]),
        tenant_id=str(value["tenant_id"]),
        name=str(value["name"]),
        members=tuple(
            _crew_member_from_dict(dict(item)) for item in value.get("members", ())
        ),
        skills=tuple(str(item) for item in value.get("skills", ())),
        active=bool(value.get("active", True)),
    )


def _crew_availability_from_dict(value: dict[str, object]) -> CrewAvailability:
    return CrewAvailability(
        availability_id=str(value["availability_id"]),
        tenant_id=str(value["tenant_id"]),
        crew_id=str(value["crew_id"]),
        start_date=str(value["start_date"]),
        end_date=str(value["end_date"]),
        status=str(value["status"]),
        note=str(value.get("note", "")),
    )


def _crew_assignment_from_dict(value: dict[str, object]) -> CrewAssignment:
    return CrewAssignment(
        assignment_id=str(value["assignment_id"]),
        tenant_id=str(value["tenant_id"]),
        crew_id=str(value["crew_id"]),
        job_id=str(value["job_id"]),
        schedule_id=str(value["schedule_id"]),
        phase_id=str(value["phase_id"]),
        start_date=str(value["start_date"]),
        end_date=str(value["end_date"]),
        status=str(value.get("status", "assigned")),
    )


def _material_delivery_from_dict(value: dict[str, object]) -> MaterialDelivery:
    return MaterialDelivery(
        delivery_id=str(value["delivery_id"]),
        tenant_id=str(value["tenant_id"]),
        job_id=str(value["job_id"]),
        schedule_id=str(value["schedule_id"]),
        phase_id=str(value["phase_id"]),
        material=str(value["material"]),
        quantity=float(value["quantity"]),
        unit=str(value["unit"]),
        required_date=str(value["required_date"]),
        expected_date=str(value["expected_date"]),
        actual_date=str(value.get("actual_date", "")),
        status=str(value["status"]),
        supplier_reference=str(value.get("supplier_reference", "")),
    )


def _phase_dependency_from_dict(value: dict[str, object]) -> PhaseDependency:
    return PhaseDependency(
        predecessor_phase_id=str(value["predecessor_phase_id"]),
        successor_phase_id=str(value["successor_phase_id"]),
        dependency_type=str(value.get("dependency_type", "finish_to_start")),
        lag_days=int(value.get("lag_days", 0)),
    )


def _schedule_phase_from_dict(value: dict[str, object]) -> SchedulePhase:
    return SchedulePhase(
        phase_id=str(value["phase_id"]),
        name=str(value["name"]),
        sequence=int(value["sequence"]),
        duration_days=int(value["duration_days"]),
        planned_start=str(value["planned_start"]),
        planned_end=str(value["planned_end"]),
        status=str(value["status"]),
        crew_assignment_ids=tuple(
            str(item) for item in value.get("crew_assignment_ids", ())
        ),
        delivery_ids=tuple(str(item) for item in value.get("delivery_ids", ())),
        blocked_reasons=tuple(str(item) for item in value.get("blocked_reasons", ())),
    )


def _schedule_conflict_from_dict(value: dict[str, object]) -> ScheduleConflict:
    return ScheduleConflict(
        conflict_id=str(value["conflict_id"]),
        conflict_type=str(value["conflict_type"]),
        severity=str(value["severity"]),
        phase_id=str(value["phase_id"]),
        reference_id=str(value["reference_id"]),
        description=str(value["description"]),
    )


def _delay_impact_from_dict(value: dict[str, object]) -> DelayImpact:
    return DelayImpact(
        delay_id=str(value["delay_id"]),
        schedule_id=str(value["schedule_id"]),
        source_type=str(value["source_type"]),
        source_id=str(value["source_id"]),
        phase_id=str(value["phase_id"]),
        delay_days=int(value["delay_days"]),
        original_completion_date=str(value["original_completion_date"]),
        projected_completion_date=str(value["projected_completion_date"]),
        summary=str(value["summary"]),
    )


def _schedule_from_dict(value: dict[str, object]) -> Schedule:
    return Schedule(
        schedule_id=str(value["schedule_id"]),
        tenant_id=str(value["tenant_id"]),
        job_id=str(value["job_id"]),
        start_date=str(value["start_date"]),
        original_completion_date=str(value["original_completion_date"]),
        projected_completion_date=str(value["projected_completion_date"]),
        status=str(value["status"]),
        revision=int(value["revision"]),
        phases=tuple(
            _schedule_phase_from_dict(dict(item)) for item in value.get("phases", ())
        ),
        dependencies=tuple(
            _phase_dependency_from_dict(dict(item))
            for item in value.get("dependencies", ())
        ),
        conflicts=tuple(
            _schedule_conflict_from_dict(dict(item))
            for item in value.get("conflicts", ())
        ),
        delay_impacts=tuple(
            _delay_impact_from_dict(dict(item))
            for item in value.get("delay_impacts", ())
        ),
        schedule_hash=str(value["schedule_hash"]),
    )


def _actual_material_cost_from_dict(value: object) -> ActualMaterialCost | None:
    if value is None:
        return None
    return ActualMaterialCost(**dict(value))


def _actual_labor_cost_from_dict(value: object) -> ActualLaborCost | None:
    if value is None:
        return None
    return ActualLaborCost(**dict(value))


def _subcontractor_cost_from_dict(value: object) -> SubcontractorCost | None:
    if value is None:
        return None
    return SubcontractorCost(**dict(value))


def _overhead_allocation_from_dict(value: object) -> OverheadAllocation | None:
    if value is None:
        return None
    return OverheadAllocation(**dict(value))


def _job_cost_from_dict(value: dict[str, object]) -> JobCostRecord:
    return JobCostRecord(
        cost_record_id=str(value["cost_record_id"]),
        tenant_id=str(value["tenant_id"]),
        job_id=str(value["job_id"]),
        cost_date=str(value["cost_date"]),
        category=str(value["category"]),
        description=str(value["description"]),
        amount=float(value["amount"]),
        source_reference=str(value.get("source_reference", "")),
        material=_actual_material_cost_from_dict(value.get("material")),
        labor=_actual_labor_cost_from_dict(value.get("labor")),
        subcontractor=_subcontractor_cost_from_dict(value.get("subcontractor")),
        overhead=_overhead_allocation_from_dict(value.get("overhead")),
    )


def _payment_from_dict(value: dict[str, object]) -> PaymentRecord:
    return PaymentRecord(
        payment_id=str(value["payment_id"]),
        tenant_id=str(value["tenant_id"]),
        target_type=str(value["target_type"]),
        target_id=str(value["target_id"]),
        payment_date=str(value["payment_date"]),
        amount=float(value["amount"]),
        method=str(value["method"]),
        reference=str(value.get("reference", "")),
    )


def _invoice_from_dict(value: dict[str, object]) -> Invoice:
    return Invoice(
        invoice_id=str(value["invoice_id"]),
        tenant_id=str(value["tenant_id"]),
        job_id=str(value["job_id"]),
        customer_id=str(value["customer_id"]),
        invoice_date=str(value["invoice_date"]),
        due_date=str(value["due_date"]),
        description=str(value["description"]),
        amount=float(value["amount"]),
        tax=float(value["tax"]),
        total=float(value["total"]),
        paid_amount=float(value["paid_amount"]),
        outstanding_balance=float(value["outstanding_balance"]),
        status=str(value["status"]),
        payment_records=tuple(
            _payment_from_dict(dict(item)) for item in value.get("payment_records", ())
        ),
    )


def _vendor_payable_from_dict(value: dict[str, object]) -> VendorPayable:
    return VendorPayable(
        payable_id=str(value["payable_id"]),
        tenant_id=str(value["tenant_id"]),
        job_id=str(value["job_id"]),
        vendor=str(value["vendor"]),
        payable_date=str(value["payable_date"]),
        due_date=str(value["due_date"]),
        description=str(value["description"]),
        amount=float(value["amount"]),
        paid_amount=float(value["paid_amount"]),
        outstanding_balance=float(value["outstanding_balance"]),
        status=str(value["status"]),
        payment_records=tuple(
            _payment_from_dict(dict(item)) for item in value.get("payment_records", ())
        ),
    )


def _margin_variance_from_dict(value: object) -> MarginVariance | None:
    if value is None:
        return None
    return MarginVariance(**dict(value))


def _cost_overrun_from_dict(value: object) -> CostOverrunAlert | None:
    if value is None:
        return None
    return CostOverrunAlert(**dict(value))


def _profitability_scorecard_from_dict(
    value: dict[str, object],
) -> ProfitabilityScorecard:
    return ProfitabilityScorecard(
        scorecard_id=str(value["scorecard_id"]),
        tenant_id=str(value["tenant_id"]),
        job_id=str(value["job_id"]),
        contracted_revenue=float(value["contracted_revenue"]),
        estimated_cost=float(value["estimated_cost"]),
        actual_cost=float(value["actual_cost"]),
        estimated_gross_profit=float(value["estimated_gross_profit"]),
        actual_gross_profit=float(value["actual_gross_profit"]),
        estimated_margin_percentage=float(value["estimated_margin_percentage"]),
        actual_margin_percentage=float(value["actual_margin_percentage"]),
        cost_variance=float(value["cost_variance"]),
        profitability_score=float(value["profitability_score"]),
        margin_variance=_margin_variance_from_dict(value.get("margin_variance")),
        cost_overrun_alert=_cost_overrun_from_dict(value.get("cost_overrun_alert")),
        financial_hash=str(value["financial_hash"]),
    )


def _cash_flow_window_from_dict(value: dict[str, object]) -> CashFlowWindow:
    return CashFlowWindow(
        days=int(value["days"]),
        through_date=str(value["through_date"]),
        receivables=float(value["receivables"]),
        payables=float(value["payables"]),
        net_cash_flow=float(value["net_cash_flow"]),
        cumulative_net_cash_flow=float(value["cumulative_net_cash_flow"]),
    )


def _cash_flow_forecast_from_dict(value: dict[str, object]) -> CashFlowForecast:
    return CashFlowForecast(
        forecast_id=str(value["forecast_id"]),
        tenant_id=str(value["tenant_id"]),
        as_of_date=str(value["as_of_date"]),
        windows=tuple(
            _cash_flow_window_from_dict(dict(item))
            for item in value.get("windows", ())
        ),
        overdue_receivables=float(value["overdue_receivables"]),
        overdue_payables=float(value["overdue_payables"]),
        forecast_hash=str(value["forecast_hash"]),
    )


def _lead_source_from_dict(value: dict[str, object]) -> LeadSource:
    return LeadSource(
        source_type=str(value["source_type"]),
        source_name=str(value["source_name"]),
        campaign=str(value.get("campaign", "")),
        referral_name=str(value.get("referral_name", "")),
    )


def _lead_from_dict(value: dict[str, object]) -> Lead:
    return Lead(
        lead_id=str(value["lead_id"]),
        tenant_id=str(value["tenant_id"]),
        name=str(value["name"]),
        email=str(value.get("email", "")),
        phone=str(value.get("phone", "")),
        property_address=str(value.get("property_address", "")),
        project_type=str(value["project_type"]),
        description=str(value.get("description", "")),
        status=str(value["status"]),
        source=_lead_source_from_dict(dict(value["source"])),
        created_date=str(value["created_date"]),
        last_contact_date=str(value.get("last_contact_date", "")),
        lost_reason=str(value.get("lost_reason", "")),
        customer_id=str(value.get("customer_id", "")),
    )


def _opportunity_from_dict(value: dict[str, object]) -> Opportunity:
    return Opportunity(
        opportunity_id=str(value["opportunity_id"]),
        tenant_id=str(value["tenant_id"]),
        lead_id=str(value.get("lead_id", "")),
        customer_id=str(value.get("customer_id", "")),
        project_type=str(value["project_type"]),
        expected_value=float(value["expected_value"]),
        probability=float(value["probability"]),
        stage=str(value["stage"]),
        expected_close_date=str(value["expected_close_date"]),
        weighted_value=float(value["weighted_value"]),
    )


def _appointment_from_dict(value: dict[str, object]) -> AppointmentRequest:
    return AppointmentRequest(
        appointment_id=str(value["appointment_id"]),
        tenant_id=str(value["tenant_id"]),
        lead_id=str(value.get("lead_id", "")),
        customer_id=str(value.get("customer_id", "")),
        requested_date=str(value["requested_date"]),
        requested_time=str(value.get("requested_time", "")),
        appointment_type=str(value["appointment_type"]),
        property_address=str(value["property_address"]),
        status=str(value["status"]),
        notes=str(value.get("notes", "")),
    )


def _customer_message_from_dict(value: dict[str, object]) -> CustomerMessage:
    return CustomerMessage(
        message_id=str(value["message_id"]),
        tenant_id=str(value["tenant_id"]),
        customer_id=str(value["customer_id"]),
        job_id=str(value.get("job_id", "")),
        channel=str(value["channel"]),
        direction=str(value["direction"]),
        message_date=str(value["message_date"]),
        subject=str(value.get("subject", "")),
        body=str(value["body"]),
        visibility=str(value["visibility"]),
    )


def _visibility_policy_from_dict(
    value: dict[str, object],
) -> CustomerVisibilityPolicy:
    return CustomerVisibilityPolicy(
        policy_id=str(value["policy_id"]),
        version=str(value["version"]),
        allowed_sections=tuple(str(item) for item in value["allowed_sections"]),
        require_photo_approval=bool(value["require_photo_approval"]),
        exclude_internal_notes=bool(value["exclude_internal_notes"]),
        exclude_internal_financials=bool(value["exclude_internal_financials"]),
    )


def _portal_view_from_dict(value: dict[str, object]) -> CustomerPortalView:
    return CustomerPortalView(
        portal_view_id=str(value["portal_view_id"]),
        tenant_id=str(value["tenant_id"]),
        customer_id=str(value["customer_id"]),
        generated_date=str(value["generated_date"]),
        policy_id=str(value["policy_id"]),
        projects=tuple(dict(item) for item in value.get("projects", ())),
        communications=tuple(
            dict(item) for item in value.get("communications", ())
        ),
        view_hash=str(value["view_hash"]),
    )
