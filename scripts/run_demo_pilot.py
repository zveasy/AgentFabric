"""Run the end-to-end Generation 11 pilot demonstration."""
# ruff: noqa: E402

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentfabric.audit_bundle import AuditBundleExporter
from agentfabric.collaboration import ContextStore, MeshWorkflowEngine, TaskGraph, TaskNode
from agentfabric.governance import ConsensusPolicy, GovernancePolicy, Proposal, Vote
from agentfabric.reference_agents import DEMO_ORG_ID, DEMO_TENANT_ID
from scripts.bootstrap_demo_tenant import build_demo_state


def _pilot_graph(workflow_id: str = "pilot-document-review") -> TaskGraph:
    return TaskGraph(
        graph_id=workflow_id,
        nodes=(
            TaskNode(
                node_id="plan",
                agent_id="workflow-planner-agent",
                capability="planning",
                payload={"goal": "review customer pilot document"},
            ),
            TaskNode(
                node_id="research",
                agent_id="research-agent",
                capability="research",
                dependencies=("plan",),
                payload={"question": "summarize relevant controls", "veil_reference": "veil-ref-document"},
            ),
            TaskNode(
                node_id="analyze",
                agent_id="document-analysis-agent",
                capability="analysis",
                dependencies=("research",),
                payload={"document_ref": "veil-doc-ref", "task": "extract obligations"},
            ),
            TaskNode(
                node_id="approval",
                agent_id="human-approval-agent",
                capability="review",
                dependencies=("analyze",),
                payload={"reason": "approve pilot evidence package"},
                requires_human_approval=True,
            ),
            TaskNode(
                node_id="compliance",
                agent_id="compliance-review-agent",
                capability="review",
                dependencies=("approval",),
                payload={"framework": "SOC2"},
            ),
        ),
    )


def _node_runner(node: TaskNode, payload: dict[str, object]) -> dict[str, object]:
    return {
        "agent_id": node.agent_id,
        "node_id": node.node_id,
        "status": "completed",
        "summary": f"{node.capability} completed with VEIL references only",
        "veil_reference": payload.get("node_payload", {}).get("veil_reference", "veil-ref-pilot"),
    }


def run_demo_pilot() -> dict[str, Any]:
    state = build_demo_state()
    context_store = ContextStore()
    engine = MeshWorkflowEngine(context_store=context_store, event_store=state.event_store)
    initial_payload = {
        "tenant_id": DEMO_TENANT_ID,
        "organization_id": DEMO_ORG_ID,
        "request": "pilot document review",
        "veil_reference": "veil-ref-document",
    }

    paused = engine.start(task_graph=_pilot_graph(), initial_payload=initial_payload, node_runner=_node_runner)
    resumed = engine.start(
        task_graph=_pilot_graph(),
        initial_payload=initial_payload,
        node_runner=_node_runner,
        approved_nodes={"approval"},
    )

    proposal = state.governance.create_proposal(
        Proposal(
            proposal_id="proposal-pilot-document-review",
            tenant_id=DEMO_TENANT_ID,
            organization_id=DEMO_ORG_ID,
            proposing_agent_id="workflow-planner-agent",
            target_org_id="gov-org-demo",
            target_team_id="gov-team-demo-review",
            action_type="new_workflow_execution",
            risk_level="medium",
            required_approvals=1,
            veil_trust_metadata_ref="veil-trust-pilot",
            consensus_mode="single_approver",
            created_by="pilot-owner",
        ),
        assigned_reviewer="pilot-owner",
    )
    _vote, consensus, approved = state.governance.cast_vote(
        Vote(
            proposal_id=proposal.proposal_id,
            tenant_id=DEMO_TENANT_ID,
            voter_agent_id="compliance-review-agent",
            voter_role="compliance_reviewer",
            vote="approve",
            reason="pilot evidence is scoped to VEIL references",
        ),
        policy=ConsensusPolicy(mode="single_approver", required_roles=("compliance_reviewer",), required_approvals=1),
        governance_policy=GovernancePolicy(
            policy_id="policy-demo",
            tenant_id=DEMO_TENANT_ID,
            organization_id=DEMO_ORG_ID,
        ),
    )
    decision_record = state.governance.execute(
        approved.proposal_id,
        action_payload={"workflow_id": "pilot-document-review", "result": resumed["status"]},
        require_human=False,
    )

    state.persistence.put(
        "runtime_jobs",
        "job-pilot-workflow",
        {
            "job_id": "job-pilot-workflow",
            "tenant_id": DEMO_TENANT_ID,
            "organization_id": DEMO_ORG_ID,
            "job_type": "workflow_step",
            "status": "completed",
            "workflow_id": "pilot-document-review",
        },
    )
    state.persistence.put(
        "reputation",
        "pilot-reputation-summary",
        {
            "tenant_id": DEMO_TENANT_ID,
            "organization_id": DEMO_ORG_ID,
            "agent_id": "workflow-planner-agent",
            "reputation_score": 1.0,
            "confidence_score": 0.95,
        },
    )

    audit_bundle = AuditBundleExporter(persistence=state.persistence, event_store=state.event_store).export(DEMO_TENANT_ID)
    bundle_dict = audit_bundle.as_dict()
    return {
        "bootstrap": state.summary,
        "workflow": {"paused": paused, "resumed": resumed},
        "governance": {"proposal": proposal.as_dict(), "consensus": consensus.as_dict(), "decision_record": decision_record.as_dict()},
        "events": {"count": len(state.event_store.replay()), "integrity_valid": state.event_store.validate_integrity()},
        "audit_bundle": bundle_dict,
    }


def main() -> None:
    output = run_demo_pilot()
    artifact_path = ROOT / "examples" / "demo_pilot_audit_bundle.json"
    artifact_path.write_text(json.dumps(output["audit_bundle"], indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
