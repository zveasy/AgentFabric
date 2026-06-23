from __future__ import annotations

import unittest

from agentfabric.audit_bundle import AuditBundleExporter

from tests.renovation_helpers import (
    AVAILABILITY_PAYLOAD,
    DELIVERY_PAYLOAD,
    schedule_fixture,
)


class RenovationSchedulingEventTests(unittest.TestCase):
    def test_events_and_audit_bundle_include_reproducible_evidence(self) -> None:
        persistence, events, service, context, _, _, job, schedule, crew = schedule_fixture()
        service.update_crew_availability(context, crew.crew_id, AVAILABILITY_PAYLOAD)
        assignment = service.create_crew_assignment(
            context,
            {
                "crew_id": crew.crew_id,
                "schedule_id": schedule.schedule_id,
                "phase_id": schedule.phases[0].phase_id,
            },
        )
        service.create_material_delivery(
            context,
            {
                **DELIVERY_PAYLOAD,
                "schedule_id": schedule.schedule_id,
                "phase_id": schedule.phases[0].phase_id,
            },
        )
        service.recalculate_schedule(context, schedule.schedule_id, {})
        service.schedule_summary(context, job.job_id)
        service.unassign_crew(context, assignment.assignment_id)
        event_types = {event.event_type for event in events.replay()}
        for event_type in {
            "renovation.schedule_created",
            "renovation.schedule_updated",
            "renovation.crew_created",
            "renovation.crew_assigned",
            "renovation.crew_unassigned",
            "renovation.crew_availability_updated",
            "renovation.material_delivery_created",
            "renovation.delay_detected",
            "renovation.schedule_recalculated",
        }:
            self.assertIn(event_type, event_types)
        self.assertTrue(events.validate_integrity())
        bundle = AuditBundleExporter(
            persistence=persistence,
            event_store=events,
        ).export("tenant-a").as_dict()
        for key in {
            "renovation_schedules",
            "renovation_schedule_recalculations",
            "renovation_schedule_summaries",
            "renovation_crews",
            "renovation_crew_assignments",
            "renovation_crew_availability",
            "renovation_material_deliveries",
            "renovation_delay_impacts",
        }:
            self.assertTrue(bundle[key], key)
