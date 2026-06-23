from __future__ import annotations

import unittest

from tests.renovation_helpers import (
    JOB_PAYLOAD,
    PROPOSAL_PAYLOAD,
    job_fixture,
    service_fixture,
    ESTIMATE_PAYLOAD,
)


class RenovationJobTests(unittest.TestCase):
    def test_job_creation_from_accepted_proposal_and_replay(self) -> None:
        _, _, service, context, _, proposal, job = job_fixture()
        self.assertEqual(job.proposal_id, proposal.proposal_id)
        self.assertEqual(job.status, "active")
        self.assertTrue(job.phases)
        self.assertEqual(job.phases[0].status, "active")
        self.assertEqual(service.replay_job(context, job.job_id), job)
        same = service.create_job(
            context,
            {**JOB_PAYLOAD, "proposal_id": proposal.proposal_id},
        )
        self.assertEqual(same.export_json(), job.export_json())

    def test_unaccepted_proposal_and_invalid_phase_fail_closed(self) -> None:
        _, _, service, context = service_fixture()
        estimate = service.create_estimate(context, ESTIMATE_PAYLOAD)
        proposal = service.create_proposal(
            context,
            {**PROPOSAL_PAYLOAD, "estimate_id": estimate.estimate_id},
        )
        with self.assertRaises(ValueError):
            service.create_job(
                context,
                {
                    **JOB_PAYLOAD,
                    "accepted": False,
                    "proposal_id": proposal.proposal_id,
                },
            )
        _, _, service, context, _, _, job = job_fixture()
        with self.assertRaises(ValueError):
            service.update_job(context, job.job_id, {"current_phase": "missing"})
