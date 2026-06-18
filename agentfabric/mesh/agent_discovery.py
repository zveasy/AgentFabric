"""Capability-driven mesh discovery."""

from __future__ import annotations

from .agent_directory import AgentDirectory


class AgentDiscovery:
    def __init__(self, directory: AgentDirectory) -> None:
        self.directory = directory

    def discover(
        self,
        *,
        capability: str,
        version: str | None = None,
        healthy_only: bool = True,
    ) -> list[dict[str, object]]:
        return [
            entry.as_dict()
            for entry in self.directory.find_by_capability(
                capability,
                version=version,
                healthy_only=healthy_only,
            )
        ]
