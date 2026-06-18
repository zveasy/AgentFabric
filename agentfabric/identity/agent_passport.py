"""Portable identity bundle for mesh participation."""

from __future__ import annotations

from dataclasses import dataclass

from .agent_certificate import AgentCertificate
from .agent_identity import AgentIdentity


@dataclass(frozen=True)
class AgentPassport:
    identity: AgentIdentity
    certificate: AgentCertificate
    metadata: dict[str, object] | None = None

    def validate(self) -> bool:
        return (
            self.identity.agent_id == self.certificate.agent_id
            and self.identity.signing_fingerprint == self.certificate.signing_fingerprint
            and self.certificate.is_valid_at()
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity.as_dict(),
            "certificate": self.certificate.as_dict(),
            "metadata": dict(self.metadata or {}),
            "valid": self.validate(),
        }
