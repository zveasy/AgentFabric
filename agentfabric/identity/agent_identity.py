"""Stable mesh identity for an AgentFabric agent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .capability_manifest import CapabilityManifest


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class AgentIdentity:
    agent_id: str
    name: str
    version: str
    owner: str
    organization: str
    capabilities: CapabilityManifest
    signing_fingerprint: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        agent_id: str,
        name: str,
        version: str,
        owner: str,
        organization: str,
        capabilities: list[str] | tuple[str, ...],
        signing_fingerprint: str,
    ) -> "AgentIdentity":
        return cls(
            agent_id=agent_id,
            name=name,
            version=version,
            owner=owner,
            organization=organization,
            capabilities=CapabilityManifest(tuple(capabilities)),
            signing_fingerprint=signing_fingerprint,
            created_at=utc_now(),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "version": self.version,
            "owner": self.owner,
            "organization": self.organization,
            "capabilities": list(self.capabilities.capabilities),
            "signing_fingerprint": self.signing_fingerprint,
            "created_at": self.created_at.isoformat(),
        }
