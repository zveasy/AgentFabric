from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ScheduledTask:
    task_id: str
    agent_id: str
    trigger_at: datetime
    recurring: bool = False
    requires_human_approval: bool = False
