"""Bootstrap a local AgentFabric pilot tenant.

The script is intentionally local-mode: it seeds in-memory services and prints a
JSON summary that mirrors what a customer pilot would create through APIs.
"""
# ruff: noqa: E402

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentfabric.enterprise import Membership, MembershipService, TenantService
from agentfabric.events import EventStore
from agentfabric.governance import AgentOrganization, AgentTeam, Charter, GovernanceService, HumanApprovalQueue
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.reference_agents import DEMO_ORG_ID, DEMO_TENANT_ID, all_reference_agents, signed_package_fixtures
from veil_client import MockVeilClient


DEMO_CREATED_BY = "pilot-admin"


@dataclass
class DemoTenantState:
    persistence: MemoryPersistenceStore
    event_store: EventStore
    governance: GovernanceService
    approvals: HumanApprovalQueue
    summary: dict[str, Any]


def build_demo_state() -> DemoTenantState:
    store = MemoryPersistenceStore()
    store.initialize()
    events = EventStore(store)
    approvals = HumanApprovalQueue(store)
    governance = GovernanceService(
        persistence=store,
        event_store=events,
        veil_client=MockVeilClient(),
        approvals=approvals,
    )

    tenant = TenantService(store).create_tenant(
        tenant_id=DEMO_TENANT_ID,
        organization_id=DEMO_ORG_ID,
        name="AgentFabric Pilot Tenant",
        created_by=DEMO_CREATED_BY,
        billing_plan="team",
    )
    events.append("tenant.created", tenant.tenant_id, tenant.as_dict())

    memberships = MembershipService(store)
    seeded_members = [
        memberships.add(
            Membership(
                principal_id="pilot-owner",
                tenant_id=DEMO_TENANT_ID,
                organization_id=DEMO_ORG_ID,
                role="owner",
                member_type="user",
                created_by=DEMO_CREATED_BY,
            )
        ),
        memberships.add(
            Membership(
                principal_id="pilot-service-account",
                tenant_id=DEMO_TENANT_ID,
                organization_id=DEMO_ORG_ID,
                role="service_account",
                member_type="service_account",
                created_by=DEMO_CREATED_BY,
            )
        ),
    ]

    quota_policy = {
        "quota_id": "demo-quota",
        "tenant_id": DEMO_TENANT_ID,
        "organization_id": DEMO_ORG_ID,
        "agents": 25,
        "workflow_runs_per_day": 100,
        "concurrent_workflows": 5,
        "mesh_messages_per_minute": 250,
        "memory_records": 1000,
        "event_retention_days": 90,
        "marketplace_installs": 25,
        "api_calls_per_day": 5000,
        "storage_bytes": 1_000_000_000,
        "compute_seconds": 50_000,
    }
    store.put("quota_policies", "demo-quota", quota_policy)
    store.put(
        "billing_records",
        "demo-billing",
        {
            "billing_id": "demo-billing",
            "tenant_id": DEMO_TENANT_ID,
            "organization_id": DEMO_ORG_ID,
            "plan": "team",
            "status": "active",
        },
    )

    agent_manifests = [agent.manifest(DEMO_TENANT_ID) for agent in all_reference_agents()]
    for manifest in agent_manifests:
        store.put("agents", str(manifest["agent_id"]), {**manifest, "tenant_id": DEMO_TENANT_ID, "organization_id": DEMO_ORG_ID})
        events.append("agent.registered", str(manifest["agent_id"]), {"tenant_id": DEMO_TENANT_ID, "manifest": manifest})

    package_fixtures = signed_package_fixtures(DEMO_TENANT_ID)
    for fixture in package_fixtures:
        package_id = str(fixture["manifest"]["package_id"])
        store.put("marketplace_packages", package_id, {**fixture, "tenant_id": DEMO_TENANT_ID, "organization_id": DEMO_ORG_ID})
        store.put(
            "marketplace_installs",
            package_id,
            {
                "install_id": f"install-{package_id}",
                "tenant_id": DEMO_TENANT_ID,
                "organization_id": DEMO_ORG_ID,
                "package_id": package_id,
                "version": fixture["manifest"]["version"],
                "signature": fixture["signature"],
                "veil_reference": "veil-ref-marketplace-install",
            },
        )
        events.append("marketplace.package.installed", package_id, {"tenant_id": DEMO_TENANT_ID, "package_id": package_id})

    org = governance.create_org(
        AgentOrganization(
            org_id="gov-org-demo",
            tenant_id=DEMO_TENANT_ID,
            organization_id=DEMO_ORG_ID,
            name="Pilot Governance Org",
            authority_boundaries=("pilot-workflows", "signed-reference-packages"),
            allowed_workflow_types=("document_review", "code_review", "marketplace_package_approval"),
            budget_limits={"workflow_runs_per_day": 100},
            created_by=DEMO_CREATED_BY,
        )
    )
    team = governance.create_team(
        AgentTeam(
            team_id="gov-team-demo-review",
            org_id=org.org_id,
            tenant_id=DEMO_TENANT_ID,
            organization_id=DEMO_ORG_ID,
            name="Pilot Review Team",
            roles={
                "workflow-planner-agent": "planner",
                "research-agent": "researcher",
                "document-analysis-agent": "reviewer",
                "compliance-review-agent": "compliance_reviewer",
                "human-approval-agent": "human_approver",
            },
            created_by=DEMO_CREATED_BY,
        )
    )
    charter = governance.update_charter(
        Charter(
            org_id=org.org_id,
            tenant_id=DEMO_TENANT_ID,
            organization_id=DEMO_ORG_ID,
            purpose="Run governed customer pilot workflows with safe audit evidence.",
            authority_boundaries=("no raw sensitive values", "VEIL references only", "human approval for high risk"),
            allowed_workflow_types=("document_review", "code_review", "compliance_review"),
            escalation_requirements=("high_risk", "external_api_call", "marketplace_publish"),
            budget_limits={"compute_seconds": 50_000},
            updated_by=DEMO_CREATED_BY,
        )
    )

    summary = {
        "organization": {"organization_id": DEMO_ORG_ID, "name": "AgentFabric Pilot Organization"},
        "tenant": tenant.as_dict(),
        "memberships": [membership.as_dict() for membership in seeded_members],
        "quotas": quota_policy,
        "billing": {"plan": "team", "status": "active"},
        "reference_agents": agent_manifests,
        "installed_packages": [fixture["manifest"]["package_id"] for fixture in package_fixtures],
        "governance": {"org": org.as_dict(), "team": team.as_dict(), "charter": charter.as_dict()},
        "event_count": len(events.replay()),
    }
    return DemoTenantState(store, events, governance, approvals, summary)


def bootstrap_demo_tenant() -> dict[str, Any]:
    return build_demo_state().summary


def main() -> None:
    print(json.dumps(bootstrap_demo_tenant(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
