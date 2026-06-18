"""Persistence-backed governance proposal service."""

from __future__ import annotations

from agentfabric.errors import AuthorizationError, ConflictError, NotFoundError
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore
from veil_client import AuditEventRequest, PolicyCheckRequest, VeilClient

from .agent_org import AgentOrganization
from .agent_team import AgentTeam
from .charter import Charter
from .consensus_engine import ConsensusEngine, ConsensusResult
from .consensus_policy import ConsensusPolicy
from .decision_record import DecisionRecord
from .governance_policy import GovernancePolicy
from .human_approval import HumanApprovalQueue
from .proposal import Proposal
from .proposal_status import ProposalStatus
from .vote import Vote


class GovernanceService:
    def __init__(
        self,
        *,
        persistence: PersistenceStore,
        event_store: EventStore,
        veil_client: VeilClient,
        approvals: HumanApprovalQueue,
    ) -> None:
        self.persistence = persistence
        self.event_store = event_store
        self.veil_client = veil_client
        self.approvals = approvals
        self.consensus = ConsensusEngine()

    def create_org(self, org: AgentOrganization) -> AgentOrganization:
        self.persistence.put("governance_orgs", org.org_id, org.as_dict())
        self.event_store.append("governance.agent_org.created", org.org_id, org.as_dict())
        return org

    def list_orgs(self, tenant_id: str) -> list[AgentOrganization]:
        return [AgentOrganization.from_dict(item) for item in self.persistence.list_tenant("governance_orgs", tenant_id)]

    def get_org(self, org_id: str) -> AgentOrganization:
        item = self.persistence.get("governance_orgs", org_id)
        if item is None:
            raise NotFoundError("governance org not found")
        return AgentOrganization.from_dict(item)

    def create_team(self, team: AgentTeam) -> AgentTeam:
        self.persistence.put("governance_teams", team.team_id, team.as_dict())
        return team

    def update_charter(self, charter: Charter) -> Charter:
        self.persistence.put("governance_charters", charter.org_id, charter.as_dict())
        self.event_store.append("governance.charter.updated", charter.org_id, charter.as_dict())
        return charter

    def create_proposal(self, proposal: Proposal, *, assigned_reviewer: str | None = None) -> Proposal:
        response = self.veil_client.check_policy(
            PolicyCheckRequest(
                agent_id=proposal.proposing_agent_id,
                action=f"governance.propose.{proposal.action_type}",
                payload=proposal.as_dict(),
            )
        )
        if not response.allowed:
            self.event_store.append(
                "governance.action.blocked",
                proposal.proposal_id,
                {"tenant_id": proposal.tenant_id, "proposal_id": proposal.proposal_id, "reason": response.reason},
            )
            raise AuthorizationError(response.reason or "VEIL policy denied proposal")
        self.persistence.put("governance_proposals", proposal.proposal_id, proposal.as_dict())
        self.event_store.append("governance.proposal.created", proposal.proposal_id, proposal.as_dict())
        if proposal.consensus_mode == "human_required" or proposal.risk_level in {"high", "critical"}:
            approval = self.approvals.request(
                proposal_id=proposal.proposal_id,
                tenant_id=proposal.tenant_id,
                assigned_reviewer=assigned_reviewer or proposal.created_by,
            )
            self.event_store.append(
                "governance.human_approval.requested",
                approval.approval_id,
                approval.as_dict(),
            )
        return proposal

    def list_proposals(self, tenant_id: str) -> list[Proposal]:
        return [Proposal.from_dict(item) for item in self.persistence.list_tenant("governance_proposals", tenant_id)]

    def get_proposal(self, proposal_id: str) -> Proposal:
        item = self.persistence.get("governance_proposals", proposal_id)
        if item is None:
            raise NotFoundError("proposal not found")
        proposal = Proposal.from_dict(item)
        if proposal.is_expired() and proposal.status not in {ProposalStatus.EXECUTED.value, ProposalStatus.REJECTED.value}:
            expired = proposal.with_status(ProposalStatus.EXPIRED.value)
            self.persistence.put("governance_proposals", proposal_id, expired.as_dict())
            return expired
        return proposal

    def cast_vote(self, vote: Vote, *, policy: ConsensusPolicy, governance_policy: GovernancePolicy) -> tuple[Vote, ConsensusResult, Proposal]:
        proposal = self.get_proposal(vote.proposal_id)
        if proposal.status in {ProposalStatus.EXECUTED.value, ProposalStatus.REJECTED.value, ProposalStatus.EXPIRED.value}:
            raise ConflictError("proposal is closed")
        if proposal.risk_level in {"high", "critical"} and vote.voter_agent_id == proposal.proposing_agent_id:
            if not governance_policy.high_risk_self_approval_allowed:
                raise AuthorizationError("self-approval is not allowed for high-risk proposals")
        self.persistence.put("governance_votes", vote.vote_id, vote.as_dict())
        self.event_store.append("governance.vote.cast", proposal.proposal_id, vote.as_dict())
        votes = self.votes_for(proposal.tenant_id, proposal.proposal_id)
        result = self.consensus.evaluate(proposal, votes, policy, governance_policy)
        status = proposal.status
        if result.status == "approved":
            status = ProposalStatus.APPROVED.value
            self.event_store.append("governance.consensus.reached", proposal.proposal_id, {"tenant_id": proposal.tenant_id, **result.as_dict()})
        elif result.status in {"rejected", "blocked", "expired", "escalated"}:
            status = result.status
            self.event_store.append("governance.consensus.failed", proposal.proposal_id, {"tenant_id": proposal.tenant_id, **result.as_dict()})
        elif result.status == "awaiting_human":
            status = ProposalStatus.AWAITING_HUMAN.value
        updated = proposal.with_status(status)
        self.persistence.put("governance_proposals", updated.proposal_id, updated.as_dict())
        return vote, result, updated

    def votes_for(self, tenant_id: str, proposal_id: str) -> list[Vote]:
        return [
            Vote.from_dict(item)
            for item in self.persistence.list_tenant("governance_votes", tenant_id)
            if item.get("proposal_id") == proposal_id
        ]

    def execute(self, proposal_id: str, *, action_payload: dict[str, object], require_human: bool) -> DecisionRecord:
        proposal = self.get_proposal(proposal_id)
        if proposal.status != ProposalStatus.APPROVED.value:
            raise ConflictError("proposal consensus is not finalized")
        if require_human and not self.approvals.approved_for_proposal(proposal.tenant_id, proposal_id):
            raise ConflictError("human approval is required")
        response = self.veil_client.check_policy(
            PolicyCheckRequest(
                agent_id=proposal.proposing_agent_id,
                action=f"governance.execute.{proposal.action_type}",
                payload={**proposal.as_dict(), "action_payload": action_payload},
            )
        )
        if not response.allowed:
            self.event_store.append(
                "governance.action.blocked",
                proposal.proposal_id,
                {"tenant_id": proposal.tenant_id, "proposal_id": proposal.proposal_id, "reason": response.reason},
            )
            raise AuthorizationError(response.reason or "VEIL policy denied execution")
        audit = self.veil_client.create_audit_event(
            AuditEventRequest(
                agent_id=proposal.proposing_agent_id,
                event_type="governance.action.executed",
                payload={"tenant_id": proposal.tenant_id, "proposal_id": proposal.proposal_id},
            )
        )
        event = self.event_store.append(
            "governance.action.executed",
            proposal.proposal_id,
            {"tenant_id": proposal.tenant_id, "proposal_id": proposal.proposal_id, "action_type": proposal.action_type},
        )
        executed = proposal.with_status(ProposalStatus.EXECUTED.value, executed_action=action_payload)
        self.persistence.put("governance_proposals", executed.proposal_id, executed.as_dict())
        votes = self.votes_for(proposal.tenant_id, proposal.proposal_id)
        approvals = [approval.as_dict() for approval in self.approvals.list(proposal.tenant_id) if approval.proposal_id == proposal.proposal_id]
        record = DecisionRecord.build(
            proposal=executed,
            votes=votes,
            consensus_result={"status": ProposalStatus.APPROVED.value},
            human_approvals=approvals,
            executed_action=action_payload,
            veil_audit_refs=(audit.event_id,),
            event_ids=(event.event_id,),
        )
        self.persistence.put("governance_decision_records", proposal.proposal_id, record.as_dict())
        return record

    def decision_record(self, proposal_id: str) -> DecisionRecord:
        item = self.persistence.get("governance_decision_records", proposal_id)
        if item is None:
            raise NotFoundError("decision record not found")
        return DecisionRecord.from_dict(item)
