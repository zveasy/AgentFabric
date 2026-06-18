"""Signed federated messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class FederatedMessage:
    source_org_id: str
    source_tenant_id: str
    destination_org_id: str
    destination_tenant_id: str
    source_agent_id: str
    destination_agent_id: str
    trust_agreement_id: str
    payload: dict[str, object]
    veil_reference: str
    signature: str
    message_id: str = field(default_factory=lambda: f"fed-msg-{uuid4().hex[:12]}")
    correlation_id: str = field(default_factory=lambda: f"fed-corr-{uuid4().hex[:12]}")
    nonce: str = field(default_factory=lambda: f"nonce-{uuid4().hex[:16]}")
    timestamp: datetime = field(default_factory=utc_now)
    ttl_seconds: int = 300
    message_type: str = "request"

    def signing_payload(self) -> dict[str, object]:
        return {
            "message_id": self.message_id,
            "source_org_id": self.source_org_id,
            "source_tenant_id": self.source_tenant_id,
            "destination_org_id": self.destination_org_id,
            "destination_tenant_id": self.destination_tenant_id,
            "source_agent_id": self.source_agent_id,
            "destination_agent_id": self.destination_agent_id,
            "trust_agreement_id": self.trust_agreement_id,
            "payload": dict(self.payload),
            "veil_reference": self.veil_reference,
            "correlation_id": self.correlation_id,
            "nonce": self.nonce,
            "timestamp": self.timestamp.isoformat(),
            "ttl_seconds": self.ttl_seconds,
            "message_type": self.message_type,
        }

    def expired(self) -> bool:
        return utc_now() > self.timestamp + timedelta(seconds=self.ttl_seconds)

    def as_dict(self) -> dict[str, object]:
        return {**self.signing_payload(), "signature": self.signature}

    @classmethod
    def sign(cls, payload: dict[str, object], secret: str) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return sha256(encoded + secret.encode("utf-8")).hexdigest()

    def verify(self, secret: str) -> bool:
        return self.signature == self.sign(self.signing_payload(), secret)

    @classmethod
    def create(cls, *, signing_secret: str, **kwargs: object) -> "FederatedMessage":
        unsigned = cls(signature="", **kwargs)
        data = unsigned.as_dict()
        data["signature"] = cls.sign(unsigned.signing_payload(), signing_secret)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "FederatedMessage":
        return cls(
            message_id=str(value["message_id"]),
            source_org_id=str(value["source_org_id"]),
            source_tenant_id=str(value["source_tenant_id"]),
            destination_org_id=str(value["destination_org_id"]),
            destination_tenant_id=str(value["destination_tenant_id"]),
            source_agent_id=str(value["source_agent_id"]),
            destination_agent_id=str(value["destination_agent_id"]),
            trust_agreement_id=str(value["trust_agreement_id"]),
            payload=dict(value.get("payload", {})),
            veil_reference=str(value.get("veil_reference", "")),
            signature=str(value.get("signature", "")),
            correlation_id=str(value.get("correlation_id", f"fed-corr-{uuid4().hex[:12]}")),
            nonce=str(value.get("nonce", f"nonce-{uuid4().hex[:16]}")),
            timestamp=datetime.fromisoformat(str(value["timestamp"])) if value.get("timestamp") else utc_now(),
            ttl_seconds=int(value.get("ttl_seconds", 300)),
            message_type=str(value.get("message_type", "request")),
        )
