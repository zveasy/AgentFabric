"""Deterministic worker task."""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerTask:
    build_id: str
    worker_id: str
    capability: str
    repository_id: str
    order: int

    def as_dict(self) -> dict[str, object]:
        return vars(self)
