from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WorkflowStep:
    step_id: str
    agent_id: str
    depends_on: tuple[str, ...] = ()
    requires_human_approval: bool = False


@dataclass(frozen=True)
class WorkflowState:
    workflow_id: str
    steps: tuple[WorkflowStep, ...] = field(default_factory=tuple)
    status: str = "pending"
