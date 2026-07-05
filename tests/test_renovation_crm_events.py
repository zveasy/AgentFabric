from __future__ import annotations

import unittest

from agentfabric.audit_bundle import AuditBundleExporter

from tests.renovation_helpers import (
    APPOINTMENT_PAYLOAD,
    FOLLOW_UP_PAYLOAD,
    LEAD_PAYLOAD,
    OPPORTUNITY_PAYLOAD,
    job_fixture,
)


class RenovationCrmEventTests(unittest.TestCase):
    def test_events_and_audit_bundle(self) -> None:
        persistence, events, service, context, _, proposal, job = job_fixture()
        lead = service.create_lead(context, LEAD_PAYLOAD)
        for status in ("contacted", "estimate_scheduled", "proposal_sent", "won"):
            service.update_lead(context, lead.lead_id, {"status": status})
        customer = service.convert_lead(context, lead.lead_id, {})
        opportunity = service.create_opportunity(
            context,
            {**OPPORTUNITY_PAYLOAD, "lead_id": lead.lead_id},
        )
        service.update_opportunity_stage(
            context,
            opportunity.opportunity_id,
            "appointment",
        )
        service.create_follow_up(
            context,
            {**FOLLOW_UP_PAYLOAD, "lead_id": lead.lead_id},
        )
        appointment = service.create_appointment(
            context,
            {**APPOINTMENT_PAYLOAD, "customer_id": customer.customer_id},
        )
        service.create_site_visit(
            context,
            {
                "appointment_id": appointment.appointment_id,
                "visit_date": "2026-08-08",
                "visited_by": "Estimator",
                "summary": "Completed site visit.",
            },
        )
        service.record_customer_message(
            context,
            {
                "customer_id": proposal.customer.customer_id,
                "job_id": job.job_id,
                "channel": "email",
                "message_date": "2026-08-08",
                "body": "Project update.",
            },
        )
        service.customer_portal_view(
            context,
            proposal.customer.customer_id,
            "2026-08-08",
        )
        event_types = {event.event_type for event in events.replay()}
        for event_type in {
            "renovation.lead_created",
            "renovation.lead_updated",
            "renovation.lead_converted",
            "renovation.opportunity_created",
            "renovation.opportunity_stage_changed",
            "renovation.follow_up_task_created",
            "renovation.appointment_requested",
            "renovation.site_visit_recorded",
            "renovation.customer_message_recorded",
            "renovation.customer_portal_view_generated",
        }:
            self.assertIn(event_type, event_types)
        bundle = AuditBundleExporter(
            persistence=persistence,
            event_store=events,
        ).export("tenant-a").as_dict()
        for key in {
            "renovation_leads",
            "renovation_customers",
            "renovation_opportunities",
            "renovation_follow_ups",
            "renovation_appointments",
            "renovation_site_visits",
            "renovation_customer_messages",
            "renovation_communications",
            "renovation_portal_views",
        }:
            self.assertTrue(bundle[key], key)
