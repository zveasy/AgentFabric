from __future__ import annotations

import unittest

from agentfabric.errors import AuthorizationError
from agentfabric.phase4.audit import ImmutableAuditLog
from agentfabric.phase4.marketplace import PrivateMarketplaceService
from agentfabric.phase4.rbac import RbacService
from agentfabric.phase4.sla import SlaCatalog


class Phase4EnterpriseTests(unittest.TestCase):
    def test_rbac_enforcement(self) -> None:
        rbac = RbacService()
        rbac.assign_role("alice", "developer")
        rbac.check("alice", "registry.publish")
        with self.assertRaises(AuthorizationError):
            rbac.check("alice", "audit.export")

    def test_immutable_audit_log(self) -> None:
        audit = ImmutableAuditLog()
        audit.append("alice", "registry.publish", "dev-a/research-agent:1.0.0")
        audit.append("alice", "runtime.run", "dev-a/research-agent:1.0.0")
        self.assertTrue(audit.verify_integrity())

    def test_private_marketplace_namespace_isolation(self) -> None:
        private_marketplace = PrivateMarketplaceService()
        private_marketplace.create_namespace("tenant-a", "tenant-a.private")
        private_marketplace.check_access("tenant-a", "tenant-a.private")
        with self.assertRaises(AuthorizationError):
            private_marketplace.check_access("tenant-b", "tenant-a.private")
        private_marketplace.grant_access("tenant-a", "tenant-a.private", "tenant-b")
        private_marketplace.check_access("tenant-b", "tenant-a.private")

    def test_sla_catalog(self) -> None:
        sla = SlaCatalog()
        tier = sla.get_tier("premium")
        self.assertEqual(tier.response_time_minutes, 60)


if __name__ == "__main__":
    unittest.main()
