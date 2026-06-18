"""Shared memory facade that does not expose internal agent memory."""

from __future__ import annotations

from .context_store import ContextStore


class SharedMemory:
    def __init__(self, context_store: ContextStore | None = None) -> None:
        self.context_store = context_store or ContextStore()

    def write_artifact(self, *, workflow_id: str, agent_id: str, key: str, value: object) -> None:
        self.context_store.put_artifact(workflow_id, f"{agent_id}:{key}", value)

    def read_artifacts(self, *, workflow_id: str) -> dict[str, object]:
        return dict(self.context_store.get_or_create(workflow_id).artifacts)

    def checkpoint(self, *, workflow_id: str, checkpoint_id: str) -> dict[str, object]:
        return self.context_store.checkpoint(workflow_id, checkpoint_id)
