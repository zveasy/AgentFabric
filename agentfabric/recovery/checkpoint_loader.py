"""Load durable workflow checkpoints."""

from __future__ import annotations

from agentfabric.persistence import PersistenceStore


class CheckpointLoader:
    def __init__(self, persistence: PersistenceStore) -> None:
        self.persistence = persistence
        self.persistence.initialize()

    def load(self, workflow_id: str, checkpoint_id: str) -> dict[str, object]:
        checkpoint = self.persistence.get("checkpoints", f"{workflow_id}:{checkpoint_id}")
        if checkpoint is None:
            raise KeyError(f"checkpoint not found: {workflow_id}:{checkpoint_id}")
        return checkpoint

    def latest(self, workflow_id: str) -> dict[str, object] | None:
        prefix = f"{workflow_id}:"
        matching = [key for key in self.persistence.keys("checkpoints") if key.startswith(prefix)]
        if not matching:
            return None
        return self.persistence.get("checkpoints", sorted(matching)[-1])
