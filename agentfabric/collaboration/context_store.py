"""Shared context store for collaborative workflows."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agentfabric.persistence import PersistenceStore


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class ContextRecord:
    workflow_id: str
    conversation_state: dict[str, object] = field(default_factory=dict)
    task_state: dict[str, object] = field(default_factory=dict)
    artifacts: dict[str, object] = field(default_factory=dict)
    structured_outputs: dict[str, object] = field(default_factory=dict)
    sanitized_payloads: dict[str, object] = field(default_factory=dict)
    veil_token_refs: list[str] = field(default_factory=list)
    approval_state: dict[str, object] = field(default_factory=dict)
    agent_visible_context: dict[str, object] = field(default_factory=dict)
    summaries: list[str] = field(default_factory=list)
    checkpoints: dict[str, dict[str, object]] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=utc_now)

    def snapshot(self) -> dict[str, object]:
        return {
            "workflow_id": self.workflow_id,
            "conversation_state": deepcopy(self.conversation_state),
            "task_state": deepcopy(self.task_state),
            "artifacts": deepcopy(self.artifacts),
            "structured_outputs": deepcopy(self.structured_outputs),
            "sanitized_payloads": deepcopy(self.sanitized_payloads),
            "veil_token_refs": list(self.veil_token_refs),
            "approval_state": deepcopy(self.approval_state),
            "agent_visible_context": deepcopy(self.agent_visible_context),
            "summaries": list(self.summaries),
            "checkpoints": deepcopy(self.checkpoints),
            "updated_at": self.updated_at.isoformat(),
        }


class ContextStore:
    def __init__(self, persistence: PersistenceStore | None = None) -> None:
        self.persistence = persistence
        self._records: dict[str, ContextRecord] = {}
        if self.persistence is not None:
            self.persistence.initialize()
            for item in self.persistence.list("shared_context"):
                record = _record_from_snapshot(item)
                self._records[record.workflow_id] = record

    def get_or_create(self, workflow_id: str) -> ContextRecord:
        if workflow_id not in self._records:
            self._records[workflow_id] = ContextRecord(workflow_id=workflow_id)
        return self._records[workflow_id]

    def update_task_state(self, workflow_id: str, node_id: str, value: dict[str, object]) -> None:
        _reject_raw_sensitive(value)
        record = self.get_or_create(workflow_id)
        record.task_state[node_id] = deepcopy(value)
        record.updated_at = utc_now()
        self._persist(record)

    def put_artifact(self, workflow_id: str, key: str, value: object) -> None:
        _reject_raw_sensitive({key: value})
        record = self.get_or_create(workflow_id)
        record.artifacts[key] = deepcopy(value)
        record.updated_at = utc_now()
        self._persist(record)

    def add_summary(self, workflow_id: str, summary: str) -> None:
        record = self.get_or_create(workflow_id)
        record.summaries.append(summary)
        record.updated_at = utc_now()
        self._persist(record)

    def put_sanitized_payload(self, workflow_id: str, key: str, value: dict[str, object]) -> None:
        _reject_raw_sensitive(value)
        record = self.get_or_create(workflow_id)
        record.sanitized_payloads[key] = deepcopy(value)
        record.updated_at = utc_now()
        self._persist(record)

    def put_structured_output(self, workflow_id: str, key: str, value: dict[str, object]) -> None:
        _reject_raw_sensitive(value)
        record = self.get_or_create(workflow_id)
        record.structured_outputs[key] = deepcopy(value)
        record.updated_at = utc_now()
        self._persist(record)

    def add_veil_token_ref(self, workflow_id: str, token_ref: str) -> None:
        record = self.get_or_create(workflow_id)
        record.veil_token_refs.append(token_ref)
        record.updated_at = utc_now()
        self._persist(record)

    def update_approval_state(self, workflow_id: str, values: dict[str, object]) -> None:
        _reject_raw_sensitive(values)
        record = self.get_or_create(workflow_id)
        record.approval_state.update(values)
        record.updated_at = utc_now()
        self._persist(record)

    def checkpoint(self, workflow_id: str, checkpoint_id: str) -> dict[str, object]:
        record = self.get_or_create(workflow_id)
        snapshot = record.snapshot()
        record.checkpoints[checkpoint_id] = snapshot
        record.updated_at = utc_now()
        self._persist(record)
        if self.persistence is not None:
            self.persistence.put("checkpoints", f"{workflow_id}:{checkpoint_id}", snapshot)
        return deepcopy(snapshot)

    def restore(self, workflow_id: str, checkpoint_id: str) -> dict[str, object]:
        record = self.get_or_create(workflow_id)
        snapshot = deepcopy(record.checkpoints[checkpoint_id])
        record.conversation_state = deepcopy(snapshot["conversation_state"])
        record.task_state = deepcopy(snapshot["task_state"])
        record.artifacts = deepcopy(snapshot["artifacts"])
        record.structured_outputs = deepcopy(snapshot.get("structured_outputs", {}))
        record.sanitized_payloads = deepcopy(snapshot.get("sanitized_payloads", {}))
        record.veil_token_refs = list(snapshot.get("veil_token_refs", []))
        record.approval_state = deepcopy(snapshot.get("approval_state", {}))
        record.agent_visible_context = deepcopy(snapshot.get("agent_visible_context", {}))
        record.summaries = list(snapshot["summaries"])
        record.updated_at = utc_now()
        self._persist(record)
        return record.snapshot()

    def _persist(self, record: ContextRecord) -> None:
        if self.persistence is not None:
            self.persistence.put("shared_context", record.workflow_id, record.snapshot())


def _record_from_snapshot(snapshot: dict[str, object]) -> ContextRecord:
    record = ContextRecord(workflow_id=str(snapshot["workflow_id"]))
    record.conversation_state = deepcopy(snapshot.get("conversation_state", {}))
    record.task_state = deepcopy(snapshot.get("task_state", {}))
    record.artifacts = deepcopy(snapshot.get("artifacts", {}))
    record.structured_outputs = deepcopy(snapshot.get("structured_outputs", {}))
    record.sanitized_payloads = deepcopy(snapshot.get("sanitized_payloads", {}))
    record.veil_token_refs = list(snapshot.get("veil_token_refs", []))
    record.approval_state = deepcopy(snapshot.get("approval_state", {}))
    record.agent_visible_context = deepcopy(snapshot.get("agent_visible_context", {}))
    record.summaries = list(snapshot.get("summaries", []))
    record.checkpoints = deepcopy(snapshot.get("checkpoints", {}))
    return record


def _reject_raw_sensitive(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"raw", "secret", "password", "token"} or lowered.startswith("raw_"):
                raise ValueError("raw sensitive values must remain behind VEIL/Aegis references")
            _reject_raw_sensitive(item)
    elif isinstance(value, list):
        for item in value:
            _reject_raw_sensitive(item)
