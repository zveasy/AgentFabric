"""Feedback capture and correction handling."""

from __future__ import annotations

from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore
from agentfabric.reputation import ReputationService

from .correction import Correction
from .feedback_record import FeedbackRecord
from .improvement_signal import ImprovementSignal


class FeedbackService:
    def __init__(self, *, persistence: PersistenceStore, event_store: EventStore, reputation: ReputationService | None = None) -> None:
        self.persistence = persistence
        self.event_store = event_store
        self.reputation = reputation
        self.persistence.initialize()

    def create(self, ctx: TenantContext, payload: dict[str, object]) -> FeedbackRecord:
        correction_id = None
        if payload.get("correction_notes"):
            correction = Correction(
                tenant_id=ctx.tenant_id,
                target_type=str(payload["target_type"]),
                target_id=str(payload["target_id"]),
                notes=str(payload["correction_notes"]),
            )
            self.persistence.put("corrections", correction.correction_id, correction.as_dict())
            correction_id = correction.correction_id
        record = FeedbackRecord(
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
            target_type=str(payload["target_type"]),
            target_id=str(payload["target_id"]),
            feedback_type=str(payload.get("feedback_type", "human_rating")),
            rating=float(payload["rating"]) if payload.get("rating") is not None else None,
            notes=str(payload.get("notes", "")),
            correction_id=correction_id,
            created_by=ctx.principal_id,
        )
        self.persistence.put("feedback", record.feedback_id, record.as_dict())
        signal = self._signal(record)
        self.persistence.put("improvement_signals", record.feedback_id, signal.as_dict())
        self.event_store.append("feedback.created", record.feedback_id, record.as_dict())
        if self.reputation and record.target_type == "agent" and record.rating is not None:
            self.reputation.record_rating(record.target_id, record.rating, tenant_id=ctx.tenant_id)
        return record

    def list(self, ctx: TenantContext) -> list[FeedbackRecord]:
        return [FeedbackRecord.from_dict(item) for item in self.persistence.list_tenant("feedback", ctx.tenant_id)]

    def get_correction(self, ctx: TenantContext, correction_id: str) -> Correction:
        item = self.persistence.get("corrections", correction_id)
        if item is None:
            raise KeyError(correction_id)
        correction = Correction.from_dict(item)
        if correction.tenant_id != ctx.tenant_id and not ctx.is_global_admin:
            raise AuthorizationError("cross-tenant correction access denied")
        return correction

    def _signal(self, record: FeedbackRecord) -> ImprovementSignal:
        severity = "high" if record.feedback_type in {"failure_report", "abuse_report"} or (record.rating is not None and record.rating < 3) else "low"
        return ImprovementSignal(
            tenant_id=record.tenant_id,
            target_type=record.target_type,
            target_id=record.target_id,
            signal_type="quality_improvement",
            severity=severity,
            summary=record.notes or record.feedback_type,
        )
