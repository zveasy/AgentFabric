from __future__ import annotations

from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.cloud import CloudRuntime, RuntimeJob
from agentfabric.cloud.queue_backends import MemoryJobQueue
from agentfabric.errors import AuthorizationError, ConflictError, ValidationError
from agentfabric.events import EventStore
from agentfabric.federation import FederatedOrg, FederationService, RemoteAgent, RemoteCapability, RemoteDelegation, TrustAgreement
from agentfabric.federation.messaging import FederatedMessage
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings
from veil_client import MockVeilClient, PolicyCheckResponse


class DenyVeilClient(MockVeilClient):
    def check_policy(self, request):
        return PolicyCheckResponse(False, "denied by veil")


class Generation9FederationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryPersistenceStore()
        self.events = EventStore(persistence=self.store)
        self.service = FederationService(persistence=self.store, event_store=self.events, veil_client=MockVeilClient())
        self.org = self.service.create_org(
            FederatedOrg(
                tenant_id="tenant-a",
                organization_id="org-a",
                remote_org_id="remote-org",
                name="Remote Org",
                endpoint="https://remote.example",
                public_key="remote-key",
                created_by="owner-a",
            )
        )

    def agreement(self, **extra) -> TrustAgreement:
        values = {
            "tenant_id": "tenant-a",
            "organization_id": "org-a",
            "remote_org_id": "remote-org",
            "created_by": "owner-a",
            "allowed_capabilities": ("research", "code_review", "compliance_review"),
        }
        values.update(extra)
        return TrustAgreement(**values)

    def active_agreement(self) -> TrustAgreement:
        created = self.service.create_agreement(self.agreement())
        return self.service.activate_agreement(created.agreement_id)

    def test_org_agreement_lifecycle_expiration_and_revocation(self) -> None:
        agreement = self.service.create_agreement(self.agreement())
        self.assertEqual(agreement.status, "draft")
        active = self.service.activate_agreement(agreement.agreement_id)
        self.assertTrue(active.is_active())
        revoked = self.service.revoke_agreement(active.agreement_id, "incident")
        self.assertEqual(revoked.status, "revoked")
        with self.assertRaises(AuthorizationError):
            self.service.publish_capability(
                RemoteAgent("tenant-a", "org-a", "remote-org", "agent", "Agent", (RemoteCapability("research"),)),
                revoked,
            )

        expired = self.service.create_agreement(self.agreement(expires_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1)))
        with self.assertRaises(ConflictError):
            self.service.activate_agreement(expired.agreement_id)

    def test_capability_filtering_message_replay_ttl_and_delegation(self) -> None:
        agreement = self.active_agreement()
        allowed = RemoteAgent(
            tenant_id="tenant-a",
            organization_id="org-a",
            remote_org_id="remote-org",
            remote_agent_id="remote-research",
            name="Remote Research",
            capabilities=(RemoteCapability("research", data_classes=("public",), package_signature_verified=True),),
            reputation_score=0.9,
        )
        denied = RemoteAgent(
            tenant_id="tenant-a",
            organization_id="org-a",
            remote_org_id="remote-org",
            remote_agent_id="remote-secret",
            name="Remote Secret",
            capabilities=(RemoteCapability("research", data_classes=("restricted",), package_signature_verified=True),),
        )
        self.service.import_capability(allowed, agreement)
        self.service.import_capability(denied, agreement)
        discovered = self.service.discover(tenant_id="tenant-a", organization_id="org-a", agreement_id=agreement.agreement_id, capability="research")
        self.assertEqual([agent.remote_agent_id for agent in discovered], ["remote-research"])

        message = FederatedMessage.create(
            signing_secret="secret",
            source_org_id="org-a",
            source_tenant_id="tenant-a",
            destination_org_id="remote-org",
            destination_tenant_id="remote-tenant",
            source_agent_id="agent-a",
            destination_agent_id="remote-research",
            trust_agreement_id=agreement.agreement_id,
            payload={"summary": "safe"},
            veil_reference="veil-ref",
        )
        receipt = self.service.send_message(message, "secret")
        self.assertEqual(receipt.status, "accepted")
        with self.assertRaises(ValidationError):
            self.service.send_message(message, "secret")
        expired = FederatedMessage.create(
            signing_secret="secret",
            source_org_id="org-a",
            source_tenant_id="tenant-a",
            destination_org_id="remote-org",
            destination_tenant_id="remote-tenant",
            source_agent_id="agent-a",
            destination_agent_id="remote-research",
            trust_agreement_id=agreement.agreement_id,
            payload={"summary": "safe"},
            veil_reference="veil-ref",
            ttl_seconds=-1,
        )
        with self.assertRaises(ValidationError):
            self.service.send_message(expired, "secret")

        with self.assertRaises(AuthorizationError):
            self.service.request_delegation(
                RemoteDelegation("tenant-a", "org-a", agreement.agreement_id, "remote-org", "agent-a", "remote-review", "code_review", {"veil_reference": "veil-ref"}, "owner-a"),
                signing_secret="secret",
                governance_approved=False,
            )
        delegated = self.service.request_delegation(
            RemoteDelegation("tenant-a", "org-a", agreement.agreement_id, "remote-org", "agent-a", "remote-review", "code_review", {"veil_reference": "veil-ref"}, "owner-a"),
            signing_secret="secret",
            governance_approved=True,
        )
        completed = self.service.complete_delegation(delegated.delegation_id, {"ok": True})
        self.assertEqual(completed.status, "completed")
        reputation = self.service.reputation("tenant-a", "remote-org")
        self.assertEqual(reputation["federated_reputation_score"], 1.0)

    def test_veil_denial_and_runtime_federation_job_guard(self) -> None:
        denied = FederationService(persistence=MemoryPersistenceStore(), event_store=EventStore(), veil_client=DenyVeilClient())
        denied.create_org(self.org)
        agreement = denied.create_agreement(self.agreement())
        active = denied.activate_agreement(agreement.agreement_id)
        message = FederatedMessage.create(
            signing_secret="secret",
            source_org_id="org-a",
            source_tenant_id="tenant-a",
            destination_org_id="remote-org",
            destination_tenant_id="remote-tenant",
            source_agent_id="agent-a",
            destination_agent_id="remote-research",
            trust_agreement_id=active.agreement_id,
            payload={"summary": "safe"},
            veil_reference="veil-ref",
        )
        with self.assertRaises(AuthorizationError):
            denied.send_message(message, "secret")

        runtime = CloudRuntime(queue=MemoryJobQueue(), persistence=self.store, event_store=self.events, veil_client=MockVeilClient())
        runtime.dispatcher.federation_check = lambda job: (_ for _ in ()).throw(AuthorizationError("no agreement"))
        with self.assertRaises(AuthorizationError):
            runtime.dispatcher.execute(RuntimeJob("tenant-a", "org-a", "owner-a", "remote_delegation", {"trust_agreement_id": "missing"}))


class Generation9FederationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "api.db"
        self.client = TestClient(
            create_app(
                Settings(
                    database_url=f"sqlite:///{db_path}",
                    production_db_path=str(Path(self.tmp.name) / "prod.db"),
                    redis_url="memory://",
                    jwt_secret="test-secret",
                    bootstrap_token="bootstrap-test-token",
                    cloud_queue_backend="memory",
                )
            )
        )
        register = self.client.post(
            "/auth/principals/register",
            json={"principal_id": "owner-a", "tenant_id": "tenant-a", "role": "owner", "scopes": []},
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        self.assertEqual(register.status_code, 200)
        token = self.client.post(
            "/auth/token/issue",
            json={"principal_id": "owner-a"},
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        self.headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
        tenant = self.client.post(
            "/tenants",
            json={"tenant_id": "tenant-a", "organization_id": "org-a", "name": "Tenant A", "billing_plan": "enterprise"},
            headers=self.headers,
        )
        self.assertEqual(tenant.status_code, 200)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def create_active_agreement(self) -> str:
        org = self.client.post(
            "/federation/orgs",
            json={"remote_org_id": "remote-org", "name": "Remote", "endpoint": "https://remote", "public_key": "key"},
            headers=self.headers,
        )
        self.assertEqual(org.status_code, 200)
        agreement = self.client.post(
            "/federation/agreements",
            json={"remote_org_id": "remote-org", "allowed_capabilities": ["research", "code_review"], "permitted_data_classes": ["public"]},
            headers=self.headers,
        )
        self.assertEqual(agreement.status_code, 200)
        activated = self.client.post(f"/federation/agreements/{agreement.json()['agreement_id']}/activate", headers=self.headers)
        self.assertEqual(activated.status_code, 200)
        return activated.json()["agreement_id"]

    def test_federation_api_flow_events_audit_and_revoke_blocking(self) -> None:
        agreement_id = self.create_active_agreement()
        imported = self.client.post(
            "/federation/capabilities/import",
            json={
                "trust_agreement_id": agreement_id,
                "remote_org_id": "remote-org",
                "remote_agent_id": "remote-research",
                "name": "Remote Research",
                "capabilities": [{"name": "research", "data_classes": ["public"]}],
                "reputation_score": 0.95,
            },
            headers=self.headers,
        )
        self.assertEqual(imported.status_code, 200)
        discovered = self.client.get(f"/federation/capabilities?agreement_id={agreement_id}&capability=research", headers=self.headers)
        self.assertEqual(discovered.json()["total"], 1)

        sent = self.client.post(
            "/federation/messages/send",
            json={
                "trust_agreement_id": agreement_id,
                "source_agent_id": "agent-a",
                "destination_agent_id": "remote-research",
                "payload": {"summary": "safe"},
                "veil_reference": "veil-ref",
                "signing_secret": "secret",
            },
            headers=self.headers,
        )
        self.assertEqual(sent.status_code, 200)
        message_id = sent.json()["message"]["message_id"]
        self.assertEqual(self.client.get(f"/federation/messages/{message_id}", headers=self.headers).status_code, 200)
        receipt = self.client.post(f"/federation/messages/{message_id}/receipt", json={"status": "accepted"}, headers=self.headers)
        self.assertEqual(receipt.status_code, 200)

        blocked = self.client.post(
            "/federation/delegations",
            json={
                "trust_agreement_id": agreement_id,
                "source_agent_id": "agent-a",
                "destination_agent_id": "remote-review",
                "task_type": "code_review",
                "payload": {"veil_reference": "veil-ref"},
            },
            headers=self.headers,
        )
        self.assertEqual(blocked.status_code, 403)
        delegated = self.client.post(
            "/federation/delegations",
            json={
                "trust_agreement_id": agreement_id,
                "source_agent_id": "agent-a",
                "destination_agent_id": "remote-review",
                "task_type": "code_review",
                "payload": {"veil_reference": "veil-ref-2"},
                "governance_approved": True,
                "signing_secret": "secret-2",
            },
            headers=self.headers,
        )
        self.assertEqual(delegated.status_code, 200)
        delegation_id = delegated.json()["delegation_id"]
        completed = self.client.post(f"/federation/delegations/{delegation_id}/complete", json={"result": {"ok": True}}, headers=self.headers)
        self.assertEqual(completed.json()["status"], "completed")
        reputation = self.client.get("/federation/reputation/remote-org", headers=self.headers)
        self.assertEqual(reputation.status_code, 200)
        self.assertEqual(reputation.json()["federated_reputation_score"], 1.0)

        audit = self.client.get("/tenants/tenant-a/audit-export", headers=self.headers)
        self.assertTrue(any(event["event_type"] == "federation.message.sent" for event in audit.json()["events"]))
        revoked = self.client.post(f"/federation/agreements/{agreement_id}/revoke", json={"reason": "incident"}, headers=self.headers)
        self.assertEqual(revoked.json()["status"], "revoked")
        after_revoke = self.client.post(
            "/federation/messages/send",
            json={"trust_agreement_id": agreement_id, "source_agent_id": "agent-a", "destination_agent_id": "remote-research", "payload": {"summary": "safe"}, "veil_reference": "veil-ref"},
            headers=self.headers,
        )
        self.assertEqual(after_revoke.status_code, 403)

    def test_tenant_isolation_rbac_and_raw_payload_rejection(self) -> None:
        agreement_id = self.create_active_agreement()
        self.assertEqual(self.client.get("/federation/orgs").status_code, 401)
        raw = self.client.post(
            "/federation/messages/send",
            json={"trust_agreement_id": agreement_id, "source_agent_id": "agent-a", "destination_agent_id": "remote", "payload": {"secret": "raw"}, "veil_reference": "veil-ref"},
            headers=self.headers,
        )
        self.assertEqual(raw.status_code, 400)


if __name__ == "__main__":
    unittest.main()
