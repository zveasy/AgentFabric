"""Deterministic customer communication history."""

from __future__ import annotations

from datetime import date
from hashlib import sha256
import json

from .models import CommunicationRecord, CustomerMessage


CHANNELS = {"call", "email", "text", "note", "portal"}
DIRECTIONS = {"inbound", "outbound", "internal"}
VISIBILITIES = {"customer", "internal"}


class CommunicationService:
    def message(
        self,
        tenant_id: str,
        payload: dict[str, object],
    ) -> tuple[CustomerMessage, CommunicationRecord]:
        channel = str(payload["channel"])
        direction = str(payload.get("direction", "outbound"))
        visibility = str(payload.get("visibility", "customer"))
        if channel not in CHANNELS:
            raise ValueError("invalid customer message channel")
        if direction not in DIRECTIONS or visibility not in VISIBILITIES:
            raise ValueError("invalid customer message direction or visibility")
        body = str(payload["body"]).strip()
        if not body:
            raise ValueError("customer message body is required")
        identity = {
            "tenant_id": tenant_id,
            "customer_id": str(payload.get("customer_id", "")),
            "job_id": str(payload.get("job_id", "")),
            "channel": channel,
            "direction": direction,
            "message_date": date.fromisoformat(str(payload["message_date"])).isoformat(),
            "subject": str(payload.get("subject", "")),
            "body": body,
            "visibility": visibility,
        }
        if not identity["customer_id"]:
            raise ValueError("customer message requires a customer")
        message = CustomerMessage(
            message_id=f"message-{_digest(identity)[:20]}",
            **identity,
        )
        record_identity = {
            "tenant_id": tenant_id,
            "lead_id": str(payload.get("lead_id", "")),
            "customer_id": message.customer_id,
            "job_id": message.job_id,
            "communication_type": channel,
            "direction": direction,
            "communication_date": message.message_date,
            "summary": str(payload.get("summary", body)),
            "visibility": visibility,
            "message_id": message.message_id,
        }
        record = CommunicationRecord(
            communication_id=f"communication-{_digest(record_identity)[:20]}",
            **record_identity,
        )
        return message, record


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
