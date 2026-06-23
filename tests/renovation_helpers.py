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


def service_fixture():
    persistence = MemoryPersistenceStore()
    events = EventStore(persistence=persistence)
    service = RenovationFoundationService(persistence, events)
    context = TenantContext("tenant-a", "org-a", "owner-a", ())
    return persistence, events, service, context
