from __future__ import annotations

import unittest

from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError

from tests.renovation_helpers import ESTIMATE_PAYLOAD, PROPOSAL_PAYLOAD, service_fixture


class RenovationTenantIsolationTests(unittest.TestCase):
    def test_cross_tenant_estimate_proposal_and_export_are_denied(self) -> None:
        _, _, service, context = service_fixture()
        estimate = service.create_estimate(context, ESTIMATE_PAYLOAD)
        proposal = service.create_proposal(
            context,
            {**PROPOSAL_PAYLOAD, "estimate_id": estimate.estimate_id},
        )
        other = TenantContext("tenant-b", "org-b", "owner-b", ())
        with self.assertRaises(AuthorizationError):
            service.get_estimate(other, estimate.estimate_id)
        with self.assertRaises(AuthorizationError):
            service.get_proposal(other, proposal.proposal_id)
        with self.assertRaises(AuthorizationError):
            service.export_proposal(other, proposal.proposal_id)

    def test_marketplace_package_metadata(self) -> None:
        _, _, service, _ = service_fixture()
        package = service.marketplace_package()
        self.assertEqual(package["name"], "RenovationOS Foundation")
        self.assertEqual(package["category"], "Construction")
        self.assertEqual(package["secondary_category"], "Operations")
        self.assertEqual(package["execution"], "offline_deterministic")
        self.assertTrue(package["tenant_isolation"])
        self.assertTrue(package["replay_support"])
