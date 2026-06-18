"""Capability-indexed directory of mesh agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from agentfabric.identity import AgentIdentity, AgentPassport


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class AgentDirectoryEntry:
    passport: AgentPassport
    health_status: str = "healthy"
    last_seen_at: datetime = field(default_factory=utc_now)

    @property
    def identity(self) -> AgentIdentity:
        return self.passport.identity

    def as_dict(self) -> dict[str, object]:
        data = self.passport.as_dict()
        data["health_status"] = self.health_status
        data["last_seen_at"] = self.last_seen_at.isoformat()
        return data


class AgentDirectory:
    def __init__(self) -> None:
        self._entries: dict[str, AgentDirectoryEntry] = {}
        self._capability_index: dict[str, list[str]] = {}

    def register(self, passport: AgentPassport, *, health_status: str = "healthy") -> AgentDirectoryEntry:
        if not passport.validate():
            raise ValueError("agent passport is not valid")
        entry = AgentDirectoryEntry(passport=passport, health_status=health_status)
        self._entries[passport.identity.agent_id] = entry
        for capability in passport.identity.capabilities.capabilities:
            indexed = self._capability_index.setdefault(capability, [])
            if passport.identity.agent_id not in indexed:
                indexed.append(passport.identity.agent_id)
        return entry

    def update_health(self, agent_id: str, health_status: str) -> None:
        entry = self._entries[agent_id]
        entry.health_status = health_status
        entry.last_seen_at = utc_now()

    def get(self, agent_id: str) -> AgentDirectoryEntry | None:
        return self._entries.get(agent_id)

    def list_agents(self) -> list[AgentDirectoryEntry]:
        return list(self._entries.values())

    def find_by_capability(
        self,
        capability: str,
        *,
        version: str | None = None,
        healthy_only: bool = True,
    ) -> list[AgentDirectoryEntry]:
        agent_ids = self._capability_index.get(capability.lower(), [])
        entries = [self._entries[agent_id] for agent_id in agent_ids]
        if version is not None:
            entries = [entry for entry in entries if _version_compatible(entry.identity.version, version)]
        if healthy_only:
            entries = [entry for entry in entries if entry.health_status == "healthy"]
        return entries


def _version_compatible(candidate: str, requested: str) -> bool:
    if requested.endswith(".x"):
        return candidate.split(".")[0] == requested.split(".")[0]
    return candidate == requested
