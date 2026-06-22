"""One deterministic repository execution step."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionStep:
    step_id: str
    order: int
    action: str
    target: str
    content_hash: str

    def as_dict(self) -> dict[str, object]:
        return vars(self)
