"""Event sourcing store for mesh and workflow recovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from uuid import uuid4

from agentfabric.persistence import PersistenceStore


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class EventType(str, Enum):
    AGENT = "agent"
    TASK = "task"
    MESSAGE = "message"
    WORKFLOW = "workflow"
    AUDIT = "audit"
    CHECKPOINT = "checkpoint"
    HUMAN_APPROVAL = "human_approval"
    REPUTATION = "reputation"
    MEMORY = "memory"


EVENT_TYPE_REGISTRY = {
    "agent.registered",
    "message.sent",
    "message.received",
    "workflow.started",
    "workflow.completed",
    "workflow.awaiting_approval",
    "task.started",
    "task.completed",
    "task.failed",
    "checkpoint.created",
    "human_approval.requested",
    "human_approval.resolved",
    "reputation.updated",
    "memory.recorded",
    "memory.deleted",
    "tenant.created",
    "team.created",
    "member.added",
    "quota.updated",
    "billing.plan_updated",
    "usage.recorded",
    "marketplace.package.published",
    "marketplace.package.signed",
    "marketplace.package.verified",
    "marketplace.package.rejected",
    "marketplace.package.installed",
    "marketplace.package.uninstalled",
    "marketplace.package.upgraded",
    "marketplace.package.rolled_back",
    "marketplace.entitlement.granted",
    "marketplace.entitlement.revoked",
    "marketplace.review.submitted",
    "marketplace.abuse_report.submitted",
    "governance.agent_org.created",
    "governance.charter.updated",
    "governance.proposal.created",
    "governance.vote.cast",
    "governance.consensus.reached",
    "governance.consensus.failed",
    "governance.human_approval.requested",
    "governance.human_approval.granted",
    "governance.human_approval.rejected",
    "governance.human_approval.escalated",
    "governance.action.executed",
    "governance.action.blocked",
    "runtime.job.created",
    "runtime.job.assigned",
    "runtime.job.started",
    "runtime.job.completed",
    "runtime.job.failed",
    "runtime.job.cancelled",
    "runtime.job.retried",
    "runtime.job.dead_lettered",
    "runtime.worker.registered",
    "runtime.worker.heartbeat_missed",
    "runtime.schedule.created",
    "runtime.schedule.triggered",
    "runtime.schedule.disabled",
    "runtime.schedule.enabled",
    "runtime.health.degraded",
    "runtime.health.recovered",
    "federation.agreement.created",
    "federation.agreement.activated",
    "federation.agreement.expired",
    "federation.agreement.revoked",
    "federation.capability.published",
    "federation.capability.imported",
    "federation.message.sent",
    "federation.message.received",
    "federation.message.rejected",
    "federation.delegation.requested",
    "federation.delegation.completed",
    "federation.delegation.failed",
    "federation.remote_org.blocked",
    "federation.remote_key.rejected",
    "connector.registered",
    "connector.enabled",
    "connector.disabled",
    "connector.execution.requested",
    "connector.execution.allowed",
    "connector.execution.denied",
    "connector.execution.completed",
    "connector.execution.failed",
    "credential.created",
    "credential.rotated",
    "credential.revoked",
    "connector.job.created",
    "connector.operation.completed",
    "connector.policy.denied",
    "connector.sync.started",
    "connector.sync.completed",
    "connector.webhook.received",
    "tool.registered",
    "tool.executed",
    "tool.policy.denied",
    "tool.approval.required",
    "tool.job.created",
    "tool.result.persisted",
    "evaluation.dataset.created",
    "evaluation.run.completed",
    "evaluation.gate.failed",
    "evaluation.gate.passed",
    "feedback.created",
    "economics.cost.recorded",
    "economics.revenue.recorded",
    "economics.spend_limit.updated",
    "economics.spend_limit.exceeded",
    "agent.metric.recorded",
    "agent.health.changed",
    "agent.drift.detected",
    "agent.anomaly.detected",
    "agent.degradation.detected",
    "agent.recommendation.created",
    "agent.version.compared",
    "factory.idea.created",
    "factory.platform.registered",
    "factory.repository.created",
    "factory.repository.updated",
    "factory.repository.deprecated",
    "factory.repository.archived",
    "factory.repository.restored",
    "factory.repository.cloned",
    "factory.repository.forked",
    "factory.artifact.generated",
    "factory.repository.packaged",
    "factory.quality.passed",
    "factory.quality.failed",
    "factory.team.task.assigned",
    "factory.execution.planned",
    "factory.execution.dry_run.completed",
    "factory.execution.approval.recorded",
    "factory.execution.step.started",
    "factory.execution.step.completed",
    "factory.execution.step.failed",
    "factory.execution.completed",
    "factory.execution.rolled_back",
    "factory.execution.replayed",
    *(item.value for item in EventType),
}


@dataclass(frozen=True)
class AgentFabricEvent:
    event_type: str
    aggregate_id: str
    payload: dict[str, object]
    event_id: str = field(default_factory=lambda: f"evt-{uuid4().hex[:12]}")
    timestamp: datetime = field(default_factory=utc_now)
    sequence: int = 0
    previous_hash: str = ""
    event_hash: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "aggregate_id": self.aggregate_id,
            "payload": dict(self.payload),
            "timestamp": self.timestamp.isoformat(),
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "AgentFabricEvent":
        timestamp = value["timestamp"]
        parsed_timestamp = datetime.fromisoformat(str(timestamp))
        return cls(
            event_id=str(value["event_id"]),
            sequence=int(value.get("sequence", 0)),
            event_type=str(value["event_type"]),
            aggregate_id=str(value["aggregate_id"]),
            payload=dict(value.get("payload", {})),
            timestamp=parsed_timestamp,
            previous_hash=str(value.get("previous_hash", "")),
            event_hash=str(value.get("event_hash", "")),
        )


class EventStore:
    def __init__(self, persistence: PersistenceStore | None = None) -> None:
        self.persistence = persistence
        self._events: list[AgentFabricEvent] = []
        if self.persistence is not None:
            self.persistence.initialize()
            self._events = [
                AgentFabricEvent.from_dict(item)
                for item in sorted(self.persistence.list("events"), key=lambda event: int(event.get("sequence", 0)))
            ]

    def append(self, event_type: str, aggregate_id: str, payload: dict[str, object]) -> AgentFabricEvent:
        if event_type not in EVENT_TYPE_REGISTRY:
            raise ValueError(f"unregistered event type: {event_type}")
        sequence = len(self._events) + 1
        previous_hash = self._events[-1].event_hash if self._events else ""
        event_id = f"evt-{uuid4().hex[:12]}"
        timestamp = utc_now()
        event_hash = _hash_event(
            {
                "event_id": event_id,
                "sequence": sequence,
                "event_type": event_type,
                "aggregate_id": aggregate_id,
                "payload": dict(payload),
                "timestamp": timestamp.isoformat(),
                "previous_hash": previous_hash,
            }
        )
        event = AgentFabricEvent(
            event_id=event_id,
            sequence=sequence,
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload=dict(payload),
            timestamp=timestamp,
            previous_hash=previous_hash,
            event_hash=event_hash,
        )
        self._events.append(event)
        if self.persistence is not None:
            self.persistence.put("events", event.event_id, event.as_dict())
        return event

    def replay(self, aggregate_id: str | None = None) -> list[AgentFabricEvent]:
        if aggregate_id is None:
            return list(self._events)
        return [event for event in self._events if event.aggregate_id == aggregate_id]

    def timeline(self) -> list[dict[str, object]]:
        return [event.as_dict() for event in sorted(self._events, key=lambda item: item.sequence)]

    def checkpoint(self, aggregate_id: str) -> dict[str, object]:
        return {
            "aggregate_id": aggregate_id,
            "events": [event.as_dict() for event in self.replay(aggregate_id)],
        }

    def get(self, event_id: str) -> AgentFabricEvent | None:
        for event in self._events:
            if event.event_id == event_id:
                return event
        return None

    def validate_integrity(self) -> bool:
        previous_hash = ""
        expected_sequence = 1
        for event in sorted(self._events, key=lambda item: item.sequence):
            if event.sequence != expected_sequence:
                return False
            if event.previous_hash != previous_hash:
                return False
            expected_hash = _hash_event(
                {
                    "event_id": event.event_id,
                    "sequence": event.sequence,
                    "event_type": event.event_type,
                    "aggregate_id": event.aggregate_id,
                    "payload": dict(event.payload),
                    "timestamp": event.timestamp.isoformat(),
                    "previous_hash": event.previous_hash,
                }
            )
            if event.event_hash != expected_hash:
                return False
            previous_hash = event.event_hash
            expected_sequence += 1
        return True


def _hash_event(value: dict[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return sha256(encoded).hexdigest()
