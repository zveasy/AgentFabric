from __future__ import annotations

import unittest

from tests.renovation_helpers import ESTIMATE_PAYLOAD, PROPOSAL_PAYLOAD, service_fixture


class RenovationProposalTests(unittest.TestCase):
    def test_proposal_is_deterministic_and_complete(self) -> None:
        _, _, service, context = service_fixture()
        estimate = service.create_estimate(context, ESTIMATE_PAYLOAD)
        payload = {**PROPOSAL_PAYLOAD, "estimate_id": estimate.estimate_id}
        first = service.create_proposal(context, payload)
        second = service.create_proposal(context, payload)
        self.assertEqual(first.export_json(), second.export_json())
        self.assertEqual(first.proposal_id, second.proposal_id)
        self.assertEqual(round(sum(item.amount for item in first.payment_schedule), 2), estimate.total)
        self.assertIn("Kitchen Remodel", first.rendered_text)
        self.assertIn("Material Estimate: $6,050.00", first.rendered_text)
        self.assertEqual(first.timeline[0].sequence, 1)
        self.assertIn("12 months", first.warranty)

    def test_export_json_and_text(self) -> None:
        _, _, service, context = service_fixture()
        estimate = service.create_estimate(context, ESTIMATE_PAYLOAD)
        proposal = service.create_proposal(
            context,
            {**PROPOSAL_PAYLOAD, "estimate_id": estimate.estimate_id},
        )
        json_export = service.export_proposal(context, proposal.proposal_id, "json")
        text_export = service.export_proposal(context, proposal.proposal_id, "text")
        self.assertEqual(json_export["content"], proposal.export_json())
        self.assertEqual(text_export["content"], proposal.rendered_text)
        self.assertNotEqual(json_export["artifact_hash"], text_export["artifact_hash"])
        with self.assertRaises(ValueError):
            service.export_proposal(context, proposal.proposal_id, "pdf")
