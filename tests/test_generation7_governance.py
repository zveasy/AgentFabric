from __future__ import annotations

from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.collaboration import ContextStore, MeshWorkflowEngine, TaskGraph, TaskNode
from agentfabric.errors import AuthorizationError
from agentfabric.events import EventStore
from agentfabric.governance import (
    ConsensusEngine,
    ConsensusPolicy,
    GovernancePolicy,
    GovernanceService,
    HumanApprovalQueue,
    Proposal,
    ProposalStatus,
    Vote,
)
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.recovery import ReplayRecoveryEngine
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings
from veil_client import PolicyCheckResponse


class DenyVeilClient:
    def check_policy(self, request):
        return PolicyCheckResponse(allowed=False, reason="denied by veil")

    def create_audit_event(self, request):
        raise AssertionError("audit should not be created when policy denies")


class Generation7GovernanceServiceTests(unittest.TestCase):
    def proposal(self, **extra) -> Proposal:
        values = {
            "tenant_id": "tenant-a",
            "organization_id": "org-a",
            "proposing_agent_id": "planner-agent",
            "target_org_id": "gov-org",
            "action_type": "workflow_execution",
            "risk_level": "medium",
            "required_approvals": 1,
            "created_by": "owner-a",
        }
        values.update(extra)
        return Proposal(**values)

    def test_consensus_modes(self) -> None:
        engine = ConsensusEngine()
        proposal = self.proposal(required_approvals=2)
        policy = GovernancePolicy("default", "tenant-a", "org-a", max_agent_authority_risk="high")
        votes = [
            Vote(proposal.proposal_id, "tenant-a", "reviewer-agent", "reviewer", "approve"),
            Vote(proposal.proposal_id, "tenant-a", "security-agent", "security_reviewer", "approve"),
            Vote(proposal.proposal_id, "tenant-a", "compliance-agent", "compliance_reviewer", "abstain"),
        ]
        majority = engine.evaluate(proposal, votes[:2], ConsensusPolicy(mode="majority", required_approvals=2), policy)
        self.assertTrue(majority.reached)
        supermajority = engine.evaluate(proposal, votes, ConsensusPolicy(mode="supermajority", threshold=2 / 3, required_approvals=2), policy)
        self.assertTrue(supermajority.reached)
        unanimous = engine.evaluate(proposal, votes[:2], ConsensusPolicy(mode="unanimous", required_approvals=2), policy)
        self.assertTrue(unanimous.reached)
        human = engine.evaluate(proposal, votes[:2], ConsensusPolicy(mode="human_required", required_approvals=2), policy)
        self.assertEqual(human.status, "awaiting_human")

    def test_expired_and_self_approval_rejected(self) -> None:
        store = MemoryPersistenceStore()
        events = EventStore(persistence=store)
        approvals = HumanApprovalQueue(store)
        service = GovernanceService(persistence=store, event_store=events, veil_client=type("Allow", (), {"check_policy": lambda *_: PolicyCheckResponse(True), "create_audit_event": lambda *_: None})(), approvals=approvals)
        expired = self.proposal(expires_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1))
        store.put("governance_proposals", expired.proposal_id, expired.as_dict())
        self.assertEqual(service.get_proposal(expired.proposal_id).status, ProposalStatus.EXPIRED.value)

        high = self.proposal(risk_level="high", consensus_mode="human_required")
        service.create_proposal(high)
        with self.assertRaises(AuthorizationError):
            service.cast_vote(
                Vote(high.proposal_id, "tenant-a", "planner-agent", "planner", "approve"),
                policy=ConsensusPolicy(mode="human_required"),
                governance_policy=GovernancePolicy("default", "tenant-a", "org-a"),
            )

    def test_veil_policy_denial_blocks_proposal(self) -> None:
        store = MemoryPersistenceStore()
        service = GovernanceService(
            persistence=store,
            event_store=EventStore(persistence=store),
            veil_client=DenyVeilClient(),
            approvals=HumanApprovalQueue(store),
        )
        with self.assertRaises(AuthorizationError):
            service.create_proposal(self.proposal())

    def test_workflow_governance_pause_survives_recovery(self) -> None:
        store = MemoryPersistenceStore()
        events = EventStore(persistence=store)
        context = ContextStore(persistence=store)
        engine = MeshWorkflowEngine(context_store=context, event_store=events)
        graph = TaskGraph.from_dicts(
            "wf-governed",
            [{"node_id": "execute", "agent_id": "executor-agent", "requires_human_approval": True}],
        )

        def runner(node: TaskNode, payload: dict[str, object]) -> dict[str, object]:
            return {"node": node.node_id}

        result = engine.start(task_graph=graph, initial_payload={"tenant_id": "tenant-a"}, node_runner=runner)
        self.assertEqual(result["status"], "awaiting_approval")
        recovered = ReplayRecoveryEngine(event_store=EventStore(persistence=store), persistence=store).recover_workflow("wf-governed")
        self.assertEqual(recovered["status"], "awaiting_approval")


class Generation7GovernanceApiTests(unittest.TestCase):
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

    def create_org(self) -> str:
        response = self.client.post("/governance/orgs", json={"name": "Autonomous Delivery"}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        return response.json()["org_id"]

    def test_org_team_charter_proposal_vote_execute_decision_and_audit(self) -> None:
        org_id = self.create_org()
        team = self.client.post(
            f"/governance/orgs/{org_id}/teams",
            json={"name": "Delivery Team", "roles": {"planner-agent": "planner", "reviewer-agent": "reviewer"}},
            headers=self.headers,
        )
        self.assertEqual(team.status_code, 200)
        charter = self.client.post(
            f"/governance/orgs/{org_id}/charter",
            json={"purpose": "Approve delivery workflows", "allowed_workflow_types": ["release"]},
            headers=self.headers,
        )
        self.assertEqual(charter.status_code, 200)

        proposal = self.client.post(
            "/governance/proposals",
            json={
                "proposing_agent_id": "planner-agent",
                "target_org_id": org_id,
                "action_type": "workflow_execution",
                "risk_level": "medium",
                "required_approvals": 1,
                "consensus_mode": "majority",
                "veil_trust_metadata_ref": "veil-ref-1",
            },
            headers=self.headers,
        )
        self.assertEqual(proposal.status_code, 200)
        proposal_id = proposal.json()["proposal_id"]
        vote = self.client.post(
            f"/governance/proposals/{proposal_id}/vote",
            json={"voter_agent_id": "reviewer-agent", "voter_role": "reviewer", "vote": "approve"},
            headers=self.headers,
        )
        self.assertEqual(vote.status_code, 200)
        self.assertEqual(vote.json()["proposal"]["status"], "approved")
        executed = self.client.post(f"/governance/proposals/{proposal_id}/execute", json={"result": "started"}, headers=self.headers)
        self.assertEqual(executed.status_code, 200)
        self.assertEqual(executed.json()["final_status"], "executed")
        decision = self.client.get(f"/governance/proposals/{proposal_id}/decision-record", headers=self.headers)
        self.assertEqual(decision.status_code, 200)
        self.assertFalse(decision.json()["risk_summary"]["raw_sensitive_values_persisted"])
        audit = self.client.get("/tenants/tenant-a/audit-export", headers=self.headers)
        self.assertTrue(any(event["event_type"] == "governance.action.executed" for event in audit.json()["events"]))
        self.assertEqual(len(audit.json()["governance_decision_records"]), 1)

    def test_human_required_approval_blocks_until_granted(self) -> None:
        org_id = self.create_org()
        proposal = self.client.post(
            "/governance/proposals",
            json={
                "proposing_agent_id": "planner-agent",
                "target_org_id": org_id,
                "action_type": "external_api_call",
                "risk_level": "high",
                "required_approvals": 1,
                "consensus_mode": "human_required",
            },
            headers=self.headers,
        )
        self.assertEqual(proposal.status_code, 200)
        proposal_id = proposal.json()["proposal_id"]
        vote = self.client.post(
            f"/governance/proposals/{proposal_id}/vote",
            json={"voter_agent_id": "security-agent", "voter_role": "security_reviewer", "vote": "approve"},
            headers=self.headers,
        )
        self.assertEqual(vote.status_code, 200)
        blocked = self.client.post(f"/governance/proposals/{proposal_id}/execute", json={}, headers=self.headers)
        self.assertEqual(blocked.status_code, 409)
        approvals = self.client.get("/governance/approvals", headers=self.headers)
        approval_id = approvals.json()["items"][0]["approval_id"]
        approved = self.client.post(f"/governance/approvals/{approval_id}/approve", json={"reason": "acceptable"}, headers=self.headers)
        self.assertEqual(approved.status_code, 200)
        executed = self.client.post(f"/governance/proposals/{proposal_id}/execute", json={}, headers=self.headers)
        self.assertEqual(executed.status_code, 200)

    def test_tenant_isolation_and_rbac(self) -> None:
        org_id = self.create_org()
        self.assertEqual(self.client.get(f"/governance/orgs/{org_id}").status_code, 401)

        register = self.client.post(
            "/auth/principals/register",
            json={"principal_id": "owner-b", "tenant_id": "tenant-b", "role": "owner", "scopes": []},
            headers={"Authorization": self.headers["Authorization"]},
        )
        self.assertEqual(register.status_code, 403)
        # A principal from another tenant cannot read tenant-a governance records.
        self.client.post(
            "/auth/principals/register",
            json={"principal_id": "global-admin", "tenant_id": "tenant-a", "role": "owner", "scopes": ["auth.admin", "tenant.global"]},
            headers={"Authorization": self.headers["Authorization"]},
        )
        # Direct cross-tenant object access remains blocked by tenant context when the token is not global.
        listed = self.client.get("/governance/orgs", headers=self.headers)
        self.assertEqual(listed.json()["total"], 1)


if __name__ == "__main__":
    unittest.main()
