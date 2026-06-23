from __future__ import annotations

from agentfabric.enterprise import TenantContext
from agentfabric.events import EventStore
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.verticals.renovation import RenovationFoundationService


ESTIMATE_PAYLOAD = {
    "project_id": "project-kitchen-1",
    "scope_description": "Cabinet replacement\nFlooring replacement",
    "rooms": [
        {
            "name": "Kitchen",
            "length_ft": 20,
            "width_ft": 15,
            "quantity": 1,
            "notes": "Main floor",
        }
    ],
    "quantities": {"cabinetry": 10, "flooring": 300},
    "labor_rate": 65,
    "contingency_percentage": 10,
    "tax_percentage": 6,
    "notes": "Offline deterministic estimate",
}

PROPOSAL_PAYLOAD = {
    "customer": {
        "customer_id": "customer-1",
        "name": "Jordan Customer",
        "email": "jordan@example.com",
        "phone": "555-0100",
        "address": "100 Main Street",
    },
    "project": {
        "project_id": "project-kitchen-1",
        "title": "Kitchen Remodel",
        "property_address": "100 Main Street",
        "notes": "Occupied residence",
    },
    "template_id": "standard_proposal",
}

JOB_PAYLOAD = {
    "accepted": True,
    "accepted_date": "2026-07-01",
    "acceptance_reference": "signed-proposal-001",
}

DAILY_LOG_PAYLOAD = {
    "work_date": "2026-07-08",
    "summary": "Completed flooring preparation and documented cabinet field conditions.",
    "weather": "Clear",
    "crew_hours": 16,
    "completed_work": ["Floor protection", "Subfloor inspection"],
    "next_steps": ["Install flooring", "Confirm cabinet dimensions"],
    "photos": [
        {
            "captured_date": "2026-07-08",
            "file_name": "kitchen-subfloor.jpg",
            "storage_reference": "veil:photo:kitchen-subfloor",
            "sha256": "a" * 64,
            "caption": "Kitchen subfloor after preparation",
            "phase_id": "phase-02",
        }
    ],
    "issues": [
        {
            "reported_date": "2026-07-08",
            "title": "Uneven subfloor",
            "description": "Localized leveling required near island.",
            "severity": "medium",
            "status": "open",
            "phase_id": "phase-02",
        }
    ],
}

FIELD_NOTE_PAYLOAD = {
    "note_date": "2026-07-08",
    "author": "Site Lead",
    "note": "Customer requested premium flooring at the kitchen island.",
    "source": "customer_request",
    "photos": [
        {
            "captured_date": "2026-07-08",
            "file_name": "island-flooring-area.jpg",
            "storage_reference": "veil:photo:island-flooring",
            "sha256": "b" * 64,
            "caption": "Area affected by flooring request",
            "phase_id": "phase-02",
        }
    ],
}

CHANGE_ORDER_PAYLOAD = {
    "source_type": "customer_request",
    "source_reference": "field-note-customer-flooring",
    "title": "Premium flooring upgrade",
    "description": "Upgrade 50 square feet to premium flooring.",
    "lines": [
        {
            "description": "Premium flooring upgrade",
            "category": "flooring",
            "quantity": 50,
            "unit": "sqft",
        }
    ],
    "schedule_delta_days": 1,
    "status": "sent",
}

SCHEDULE_PAYLOAD = {
    "start_date": "2026-07-06",
}

CREW_PAYLOAD = {
    "name": "North Crew",
    "members": [
        {
            "member_id": "member-lead",
            "name": "Alex Builder",
            "role": "lead",
            "skills": ["flooring", "cabinetry"],
        },
        {
            "member_id": "member-helper",
            "name": "Taylor Builder",
            "role": "installer",
            "skills": ["flooring"],
        },
    ],
    "skills": ["cabinetry", "flooring"],
}

AVAILABILITY_PAYLOAD = {
    "start_date": "2026-07-06",
    "end_date": "2026-07-07",
    "status": "unavailable",
    "note": "Prior committed project",
}

DELIVERY_PAYLOAD = {
    "material": "Kitchen cabinets",
    "quantity": 1,
    "unit": "lot",
    "required_date": "2026-07-06",
    "expected_date": "2026-07-09",
    "status": "delayed",
    "supplier_reference": "supplier-order-100",
}


def service_fixture():
    persistence = MemoryPersistenceStore()
    events = EventStore(persistence=persistence)
    service = RenovationFoundationService(persistence, events)
    context = TenantContext("tenant-a", "org-a", "owner-a", ())
    return persistence, events, service, context


def job_fixture():
    persistence, events, service, context = service_fixture()
    estimate = service.create_estimate(context, ESTIMATE_PAYLOAD)
    proposal = service.create_proposal(
        context,
        {**PROPOSAL_PAYLOAD, "estimate_id": estimate.estimate_id},
    )
    job = service.create_job(
        context,
        {**JOB_PAYLOAD, "proposal_id": proposal.proposal_id},
    )
    return persistence, events, service, context, estimate, proposal, job


def schedule_fixture():
    persistence, events, service, context, estimate, proposal, job = job_fixture()
    schedule = service.create_schedule(
        context,
        {**SCHEDULE_PAYLOAD, "job_id": job.job_id},
    )
    crew = service.create_crew(context, CREW_PAYLOAD)
    return persistence, events, service, context, estimate, proposal, job, schedule, crew
