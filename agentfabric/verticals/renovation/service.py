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
from .crews import Crew, CrewAssignment, CrewAvailability, CrewMember, CrewService
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
    CHANGE_ORDER_APPROVED,
    CHANGE_ORDER_CREATED,
    CHANGE_ORDER_EXPORTED,
    CHANGE_ORDER_REJECTED,
    CREW_ASSIGNED,
    CREW_AVAILABILITY_UPDATED,
    CREW_CREATED,
    CREW_UNASSIGNED,
    DAILY_LOG_CREATED,
    DELAY_DETECTED,
    ESTIMATE_CREATED,
    ESTIMATE_UPDATED,
    FIELD_NOTE_ADDED,
    ISSUE_RECORD_ADDED,
    JOB_CREATED,
    JOB_UPDATED,
    MATERIAL_DELIVERY_CREATED,
    MATERIAL_DELIVERY_UPDATED,
    PHOTO_RECORD_ADDED,
    PROPOSAL_EXPORTED,
    PROPOSAL_GENERATED,
    SCHEDULE_CREATED,
    SCHEDULE_RECALCULATED,
    SCHEDULE_UPDATED,
)
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
