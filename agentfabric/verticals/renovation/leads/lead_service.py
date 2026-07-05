"""Deterministic lead intake and lifecycle transitions."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from hashlib import sha256
import json

from .models import Lead, LeadSource


LEAD_STATUSES = (
    "new",
    "contacted",
    "appointment_requested",
    "estimate_scheduled",
    "proposal_sent",
    "won",
    "lost",
)
SOURCE_TYPES = {"manual", "website", "referral", "phone"}
ALLOWED_TRANSITIONS = {
    "new": {"contacted", "appointment_requested", "lost"},
    "contacted": {"appointment_requested", "estimate_scheduled", "lost"},
    "appointment_requested": {"contacted", "estimate_scheduled", "lost"},
    "estimate_scheduled": {"proposal_sent", "lost"},
    "proposal_sent": {"won", "lost"},
    "won": set(),
    "lost": set(),
}


class LeadService:
    def create(self, tenant_id: str, payload: dict[str, object]) -> Lead:
        name = str(payload["name"]).strip()
        project_type = str(payload["project_type"]).strip()
        created_date = date.fromisoformat(str(payload["created_date"])).isoformat()
        source_payload = dict(payload.get("source", {}))
        source_type = str(source_payload.get("source_type", payload.get("source_type", "manual")))
        if source_type not in SOURCE_TYPES:
            raise ValueError("invalid renovation lead source")
        if not name or not project_type:
            raise ValueError("lead name and project type are required")
        source = LeadSource(
            source_type=source_type,
            source_name=str(source_payload.get("source_name", source_type)),
            campaign=str(source_payload.get("campaign", "")),
            referral_name=str(source_payload.get("referral_name", "")),
        )
        identity = {
            "tenant_id": tenant_id,
            "name": name,
            "email": str(payload.get("email", "")).strip(),
            "phone": str(payload.get("phone", "")).strip(),
            "property_address": str(payload.get("property_address", "")).strip(),
            "project_type": project_type,
            "description": str(payload.get("description", "")).strip(),
            "source": source.as_dict(),
            "created_date": created_date,
        }
        return Lead(
            lead_id=f"lead-{_digest(identity)[:20]}",
            status="new",
            source=source,
            last_contact_date="",
            lost_reason="",
            customer_id="",
            **{key: value for key, value in identity.items() if key != "source"},
        )

    def update(self, lead: Lead, payload: dict[str, object]) -> Lead:
        status = str(payload.get("status", lead.status))
        if status not in LEAD_STATUSES:
            raise ValueError("invalid renovation lead status")
        if status != lead.status and status not in ALLOWED_TRANSITIONS[lead.status]:
            raise ValueError(f"invalid lead transition: {lead.status} -> {status}")
        last_contact_date = str(payload.get("last_contact_date", lead.last_contact_date))
        if last_contact_date:
            date.fromisoformat(last_contact_date)
        lost_reason = str(payload.get("lost_reason", lead.lost_reason))
        if status == "lost" and not lost_reason.strip():
            raise ValueError("lost lead requires a reason")
        return replace(
            lead,
            status=status,
            last_contact_date=last_contact_date,
            lost_reason=lost_reason,
        )

    def convert(self, lead: Lead, customer_id: str) -> Lead:
        if lead.status != "won":
            raise ValueError("only won leads may be converted")
        if lead.customer_id:
            raise ValueError("lead is already converted")
        return replace(lead, customer_id=customer_id)


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
