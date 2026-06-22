"""Multi-agent software team coordination."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore


TEAM_NAMES = (
    "Architect Team",
    "Backend Team",
    "Frontend Team",
    "Security Team",
    "Testing Team",
    "Documentation Team",
    "Deployment Team",
)


@dataclass(frozen=True)
class SoftwareTask:
    tenant_id: str
    repository_id: str
    team: str
    description: str
    assigned_agents: tuple[str, ...]
    status: str = "pending"
    task_id: str = field(default_factory=lambda: f"software-task-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def as_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "tenant_id": self.tenant_id,
            "repository_id": self.repository_id,
            "team": self.team,
            "description": self.description,
            "assigned_agents": list(self.assigned_agents),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class SoftwareTeamService:
    def __init__(self, persistence: PersistenceStore, event_store: EventStore) -> None:
        self.persistence = persistence
        self.event_store = event_store

    def assign(self, task: SoftwareTask) -> SoftwareTask:
        if task.team not in TEAM_NAMES:
            raise ValueError("unknown software team")
        if not task.assigned_agents:
            raise ValueError("software task requires assigned agents")
        self.persistence.put("factory_software_tasks", task.task_id, task.as_dict())
        self.event_store.append("factory.team.task.assigned", task.task_id, task.as_dict())
        return task

    def list(self, tenant_id: str) -> list[dict[str, object]]:
        return self.persistence.list_tenant("factory_software_tasks", tenant_id)
