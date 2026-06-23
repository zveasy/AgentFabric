from __future__ import annotations

import unittest

from tests.renovation_helpers import (
    AVAILABILITY_PAYLOAD,
    DELIVERY_PAYLOAD,
    schedule_fixture,
)


class RenovationCrewDeliveryTests(unittest.TestCase):
    def test_crew_creation_assignment_availability_and_conflict(self) -> None:
        _, _, service, context, _, _, job, schedule, crew = schedule_fixture()
        availability = service.update_crew_availability(
            context,
            crew.crew_id,
            AVAILABILITY_PAYLOAD,
        )
        assignment = service.create_crew_assignment(
            context,
            {
                "crew_id": crew.crew_id,
                "schedule_id": schedule.schedule_id,
                "phase_id": schedule.phases[0].phase_id,
            },
        )
        recalculated = service.recalculate_schedule(context, schedule.schedule_id, {})
        self.assertEqual(availability.status, "unavailable")
        self.assertEqual(assignment.job_id, job.job_id)
        self.assertTrue(recalculated.conflicts)
        self.assertEqual(recalculated.phases[0].status, "blocked")

    def test_delivery_delay_recalculates_completion_and_replays(self) -> None:
        _, _, service, context, _, _, _, schedule, _ = schedule_fixture()
        delivery = service.create_material_delivery(
            context,
            {
                **DELIVERY_PAYLOAD,
                "schedule_id": schedule.schedule_id,
                "phase_id": schedule.phases[0].phase_id,
            },
        )
        recalculated = service.recalculate_schedule(context, schedule.schedule_id, {})
        repeated = service.recalculate_schedule(context, schedule.schedule_id, {})
        self.assertEqual(delivery.status, "delayed")
        self.assertEqual(recalculated.status, "delayed")
        self.assertGreater(
            recalculated.projected_completion_date,
            recalculated.original_completion_date,
        )
        self.assertTrue(recalculated.delay_impacts)
        self.assertTrue(recalculated.phases[0].blocked_reasons)
        self.assertEqual(
            repeated.projected_completion_date,
            recalculated.projected_completion_date,
        )
        self.assertEqual(
            service.replay_schedule(context, schedule.schedule_id),
            repeated,
        )

    def test_overlapping_assignment_is_detected(self) -> None:
        _, _, service, context, _, _, _, schedule, crew = schedule_fixture()
        phase = schedule.phases[0]
        service.create_crew_assignment(
            context,
            {
                "crew_id": crew.crew_id,
                "schedule_id": schedule.schedule_id,
                "phase_id": phase.phase_id,
            },
        )
        service.create_crew_assignment(
            context,
            {
                "crew_id": crew.crew_id,
                "schedule_id": schedule.schedule_id,
                "phase_id": schedule.phases[1].phase_id,
                "start_date": phase.planned_start,
                "end_date": phase.planned_end,
            },
        )
        recalculated = service.recalculate_schedule(context, schedule.schedule_id, {})
        self.assertIn("crew_overlap", {item.conflict_type for item in recalculated.conflicts})

    def test_invalid_assignment_and_delivery_phase_fail_closed(self) -> None:
        _, _, service, context, _, _, _, schedule, crew = schedule_fixture()
        with self.assertRaises(Exception):
            service.create_crew_assignment(
                context,
                {
                    "crew_id": crew.crew_id,
                    "schedule_id": schedule.schedule_id,
                    "phase_id": "missing",
                },
            )
        with self.assertRaises(Exception):
            service.create_material_delivery(
                context,
                {
                    **DELIVERY_PAYLOAD,
                    "schedule_id": schedule.schedule_id,
                    "phase_id": "missing",
                },
            )
