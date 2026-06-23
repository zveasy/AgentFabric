"""Deterministic crew creation and assignment."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from hashlib import sha256
import json

from .models import Crew, CrewAssignment, CrewAvailability, CrewMember


AVAILABILITY_STATUSES = {"available", "unavailable", "limited"}
ASSIGNMENT_STATUSES = {"assigned", "active", "completed", "cancelled"}


class CrewService:
    def create(self, tenant_id: str, payload: dict[str, object]) -> Crew:
        name = str(payload["name"]).strip()
        if not name:
            raise ValueError("crew name is required")
        members = tuple(
            CrewMember(
                member_id=str(item.get("member_id") or f"member-{index:02d}"),
                name=str(item["name"]).strip(),
                role=str(item["role"]).strip(),
                skills=_strings(item.get("skills", ())),
            )
            for index, item in enumerate(payload.get("members", ()), start=1)
        )
        if any(not member.name or not member.role for member in members):
            raise ValueError("crew member name and role are required")
        identity = {
            "tenant_id": tenant_id,
            "name": name,
            "members": [member.as_dict() for member in members],
            "skills": sorted(_strings(payload.get("skills", ()))),
        }
        return Crew(
            crew_id=f"crew-{_digest(identity)[:20]}",
            tenant_id=tenant_id,
            name=name,
            members=members,
            skills=tuple(identity["skills"]),
            active=bool(payload.get("active", True)),
        )

    def availability(
        self,
        tenant_id: str,
        crew_id: str,
        payload: dict[str, object],
    ) -> CrewAvailability:
        start_date = _date(str(payload["start_date"]))
        end_date = _date(str(payload["end_date"]))
        status = str(payload.get("status", "available"))
        if end_date < start_date:
            raise ValueError("crew availability end date precedes start date")
        if status not in AVAILABILITY_STATUSES:
            raise ValueError("invalid crew availability status")
        identity = {
            "tenant_id": tenant_id,
            "crew_id": crew_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "status": status,
            "note": str(payload.get("note", "")),
        }
        return CrewAvailability(
            availability_id=f"availability-{_digest(identity)[:20]}",
            **identity,
        )

    def assignment(
        self,
        tenant_id: str,
        crew_id: str,
        job_id: str,
        schedule_id: str,
        phase_id: str,
        start_date: str,
        end_date: str,
        payload: dict[str, object],
    ) -> CrewAssignment:
        start = _date(start_date)
        end = _date(end_date)
        status = str(payload.get("status", "assigned"))
        if end < start:
            raise ValueError("crew assignment end date precedes start date")
        if status not in ASSIGNMENT_STATUSES:
            raise ValueError("invalid crew assignment status")
        identity = {
            "tenant_id": tenant_id,
            "crew_id": crew_id,
            "job_id": job_id,
            "schedule_id": schedule_id,
            "phase_id": phase_id,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "status": status,
        }
        return CrewAssignment(
            assignment_id=f"assignment-{_digest(identity)[:20]}",
            **identity,
        )

    def unassign(self, assignment: CrewAssignment) -> CrewAssignment:
        if assignment.status == "cancelled":
            return assignment
        return replace(assignment, status="cancelled")


def overlaps(first_start: str, first_end: str, second_start: str, second_end: str) -> bool:
    return _date(first_start) <= _date(second_end) and _date(second_start) <= _date(first_end)


def _strings(value: object) -> tuple[str, ...]:
    return tuple(sorted({str(item).strip() for item in value if str(item).strip()}))


def _date(value: str) -> date:
    return date.fromisoformat(value)


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
