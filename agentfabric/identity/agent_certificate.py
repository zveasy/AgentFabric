"""Agent signing certificate metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class AgentCertificate:
    agent_id: str
    signing_fingerprint: str
    issuer: str
    issued_at: datetime
    expires_at: datetime | None = None

    @classmethod
    def issue(
        cls,
        *,
        agent_id: str,
        signing_fingerprint: str,
        issuer: str = "agentfabric",
        expires_at: datetime | None = None,
    ) -> "AgentCertificate":
        return cls(
            agent_id=agent_id,
            signing_fingerprint=signing_fingerprint,
            issuer=issuer,
            issued_at=utc_now(),
            expires_at=expires_at,
        )

    def is_valid_at(self, when: datetime | None = None) -> bool:
        check_time = when or utc_now()
        return self.expires_at is None or self.expires_at > check_time

    def as_dict(self) -> dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "signing_fingerprint": self.signing_fingerprint,
            "issuer": self.issuer,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
