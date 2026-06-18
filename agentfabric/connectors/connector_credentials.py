"""Connector credential references.

AgentFabric stores references to credential material, never raw secrets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class ConnectorCredentials:
    credential_ref: str
    provider: str
    expires_at: datetime | None = None
    rotation_due_at: datetime | None = None

    def validate(self) -> None:
        if not self.credential_ref:
            raise ValueError("credential_ref is required")
        lowered = self.credential_ref.lower()
        if any(marker in lowered for marker in ("secret=", "password=", "token=")):
            raise ValueError("raw credential values are not allowed")

    def as_dict(self) -> dict[str, object]:
        return {
            "credential_ref": self.credential_ref,
            "provider": self.provider,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "rotation_due_at": self.rotation_due_at.isoformat() if self.rotation_due_at else None,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "ConnectorCredentials":
        return cls(
            credential_ref=str(value["credential_ref"]),
            provider=str(value.get("provider", "")),
            expires_at=datetime.fromisoformat(str(value["expires_at"])) if value.get("expires_at") else None,
            rotation_due_at=datetime.fromisoformat(str(value["rotation_due_at"])) if value.get("rotation_due_at") else None,
        )
