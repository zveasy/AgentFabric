from __future__ import annotations

import unittest

from tests.renovation_helpers import SCHEDULE_PAYLOAD, job_fixture, schedule_fixture


class RenovationSchedulingTests(unittest.TestCase):
    def test_schedule_creation_dependencies_and_deterministic_replay(self) -> None:
        _, _, service, context, _, _, job = job_fixture()
        first = service.create_schedule(
            context,
            {**SCHEDULE_PAYLOAD, "job_id": job.job_id},
        )
        second = service.create_schedule(
            context,
            {**SCHEDULE_PAYLOAD, "job_id": job.job_id},
        )
        self.assertEqual(first.export_json(), second.export_json())
        self.assertEqual(len(first.dependencies), max(0, len(first.phases) - 1))
        self.assertEqual(service.replay_schedule(context, first.schedule_id), first)
        for previous, current in zip(first.phases, first.phases[1:], strict=False):
            self.assertGreater(current.planned_start, previous.planned_end)

    def test_cycle_and_unknown_phase_fail_closed(self) -> None:
        _, _, service, context, _, _, job = job_fixture()
        first, second = job.phases[:2]
        with self.assertRaises(ValueError):
            service.create_schedule(
                context,
                {
                    "job_id": job.job_id,
                    "start_date": "2026-07-06",
                    "dependencies": [
                        {
                            "predecessor_phase_id": first.phase_id,
                            "successor_phase_id": second.phase_id,
                        },
                        {
                            "predecessor_phase_id": second.phase_id,
                            "successor_phase_id": first.phase_id,
                        },
                    ],
                },
            )
        with self.assertRaises(ValueError):
            service.create_schedule(
                context,
                {
                    "job_id": job.job_id,
                    "phase_durations": {"missing-phase": 2},
                },
            )

    def test_customer_summary_is_reproducible(self) -> None:
        _, _, service, context, _, _, job, schedule, _ = schedule_fixture()
        first = service.schedule_summary(context, job.job_id)
        second = service.schedule_summary(context, job.job_id)
        self.assertEqual(first, second)
        self.assertEqual(first["schedule_id"], schedule.schedule_id)
        self.assertEqual(len(first["summary_hash"]), 64)
