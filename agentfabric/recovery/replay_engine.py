"""Replay recovery engine for durable workflows."""

from __future__ import annotations

from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore

from .checkpoint_loader import CheckpointLoader
from .integrity_validator import IntegrityValidator
from .state_rebuilder import StateRebuilder


class ReplayRecoveryEngine:
    def __init__(self, *, event_store: EventStore, persistence: PersistenceStore | None = None) -> None:
        self.event_store = event_store
        self.persistence = persistence
        self.rebuilder = StateRebuilder()

    def recover_workflow(self, workflow_id: str) -> dict[str, object]:
        IntegrityValidator(self.event_store).validate_or_raise()
        events = self.event_store.replay(workflow_id)
        if not events:
            raise KeyError(f"workflow not found: {workflow_id}")
        state = self.rebuilder.rebuild_workflow(workflow_id, events)
        state["recovered"] = True
        state["safe_to_resume"] = state["status"] in {"running", "awaiting_approval"}
        state["skip_completed_task_ids"] = list(state["completed_task_ids"])
        if self.persistence is not None:
            latest = CheckpointLoader(self.persistence).latest(workflow_id)
            if latest is not None:
                state["latest_checkpoint"] = latest
        return state
