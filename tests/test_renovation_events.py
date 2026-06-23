from __future__ import annotations

import unittest

from agentfabric.audit_bundle import AuditBundleExporter

from tests.renovation_helpers import ESTIMATE_PAYLOAD, PROPOSAL_PAYLOAD, service_fixture


class RenovationEventTests(unittest.TestCase):
    def test_events_replay_and_audit_inclusion(self) -> None:
        persistence, events, service, context = service_fixture()
        estimate = service.create_estimate(context, ESTIMATE_PAYLOAD)
        service.create_estimate(context, ESTIMATE_PAYLOAD)
        proposal = service.create_proposal(
            context,
            {**PROPOSAL_PAYLOAD, "estimate_id": estimate.estimate_id},
        )
        service.export_proposal(context, proposal.proposal_id)
        event_types = [event.event_type for event in events.replay()]
        self.assertIn("renovation.estimate_created", event_types)
        self.assertIn("renovation.estimate_updated", event_types)
        self.assertIn("renovation.proposal_generated", event_types)
        self.assertIn("renovation.proposal_exported", event_types)
        self.assertEqual(service.replay_estimate(context, estimate.estimate_id), estimate)
        self.assertEqual(service.replay_proposal(context, proposal.proposal_id), proposal)
        self.assertTrue(events.validate_integrity())
        bundle = AuditBundleExporter(persistence=persistence, event_store=events).export("tenant-a").as_dict()
        self.assertTrue(bundle["renovation_estimates"])
        self.assertTrue(bundle["renovation_proposals"])
        self.assertTrue(bundle["renovation_proposal_exports"])
        artifact = bundle["renovation_proposals"][0]["artifact"]
        self.assertEqual(artifact["template_id"], "standard_proposal")
        self.assertTrue(artifact["timeline"])
