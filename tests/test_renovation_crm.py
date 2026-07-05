from __future__ import annotations

import unittest

from tests.renovation_helpers import (
    APPOINTMENT_PAYLOAD,
    FOLLOW_UP_PAYLOAD,
    LEAD_PAYLOAD,
    OPPORTUNITY_PAYLOAD,
    service_fixture,
)


class RenovationCrmTests(unittest.TestCase):
    def test_lead_creation_transitions_conversion_and_replay(self) -> None:
        _, _, service, context = service_fixture()
        first = service.create_lead(context, LEAD_PAYLOAD)
        second = service.create_lead(context, LEAD_PAYLOAD)
        self.assertEqual(first.export_json(), second.export_json())
        for status in (
            "contacted",
            "estimate_scheduled",
            "proposal_sent",
            "won",
        ):
            service.update_lead(
                context,
                first.lead_id,
                {"status": status, "last_contact_date": "2026-08-02"},
            )
        customer = service.convert_lead(context, first.lead_id, {})
        replayed = service.replay_lead(context, first.lead_id)
        self.assertEqual(replayed.status, "won")
        self.assertEqual(replayed.customer_id, customer.customer_id)
        with self.assertRaises(ValueError):
            service.update_lead(context, first.lead_id, {"status": "contacted"})

    def test_opportunity_follow_up_appointment_and_site_visit(self) -> None:
        _, _, service, context = service_fixture()
        lead = service.create_lead(context, LEAD_PAYLOAD)
        opportunity = service.create_opportunity(
            context,
            {**OPPORTUNITY_PAYLOAD, "lead_id": lead.lead_id},
        )
        self.assertEqual(opportunity.weighted_value, 15000)
        updated = service.update_opportunity_stage(
            context,
            opportunity.opportunity_id,
            "appointment",
        )
        self.assertEqual(updated.stage, "appointment")
        self.assertEqual(
            service.replay_opportunity(context, opportunity.opportunity_id),
            updated,
        )
        follow_up = service.create_follow_up(
            context,
            {**FOLLOW_UP_PAYLOAD, "lead_id": lead.lead_id},
        )
        self.assertEqual(follow_up.reminder_date, "2026-08-03")
        appointment = service.create_appointment(
            context,
            {**APPOINTMENT_PAYLOAD, "lead_id": lead.lead_id},
        )
        visit = service.create_site_visit(
            context,
            {
                "appointment_id": appointment.appointment_id,
                "visit_date": "2026-08-08",
                "visited_by": "Estimator",
                "summary": "Measured rooms and reviewed requested scope.",
                "next_step": "Prepare estimate.",
            },
        )
        self.assertEqual(visit.lead_id, lead.lead_id)

    def test_invalid_status_and_stage_transitions_fail_closed(self) -> None:
        _, _, service, context = service_fixture()
        lead = service.create_lead(context, LEAD_PAYLOAD)
        with self.assertRaises(ValueError):
            service.update_lead(context, lead.lead_id, {"status": "won"})
        opportunity = service.create_opportunity(
            context,
            {**OPPORTUNITY_PAYLOAD, "lead_id": lead.lead_id},
        )
        service.update_opportunity_stage(context, opportunity.opportunity_id, "proposal")
        with self.assertRaises(ValueError):
            service.update_opportunity_stage(
                context,
                opportunity.opportunity_id,
                "qualification",
            )
