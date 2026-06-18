"""Reference agents for customer pilots."""

from __future__ import annotations

from dataclasses import dataclass

from agentfabric.marketplace import PackageManifest, PackageMetadata, PackageSignature, SigningKey


DEMO_TENANT_ID = "demo-tenant"
DEMO_ORG_ID = "demo-org"
DEMO_SIGNING_SECRET = "agentfabric-demo-signing-secret"


@dataclass(frozen=True)
class ReferenceAgent:
    agent_id: str
    name: str
    version: str
    capabilities: tuple[str, ...]
    tool_permissions: tuple[str, ...]
    example_input: dict[str, object]
    example_output: dict[str, object]
    package_id: str
    description: str
    dependencies: tuple[str, ...] = ()

    def manifest(self, tenant_id: str = DEMO_TENANT_ID) -> dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "tool_permissions": list(self.tool_permissions),
            "example_input": dict(self.example_input),
            "example_output": dict(self.example_output),
            "marketplace_package": self.package_manifest(tenant_id).as_dict(),
            "metadata": self.package_metadata().as_dict(),
        }

    def package_manifest(self, tenant_id: str = DEMO_TENANT_ID) -> PackageManifest:
        return PackageManifest(
            package_id=self.package_id,
            name=self.name,
            version=self.version,
            publisher_tenant_id=tenant_id,
            agent_identity_id=self.agent_id,
            runtime_requirements={"python": ">=3.11", "agentfabric": "generation-11"},
            tool_permissions=self.tool_permissions,
            license_type="free",
            pricing_model="pilot",
        )

    def package_metadata(self) -> PackageMetadata:
        return PackageMetadata(
            description=self.description,
            tags=self.capabilities,
            private=False,
            high_risk_approved=False,
        )

    def signed_package_fixture(self, tenant_id: str = DEMO_TENANT_ID) -> dict[str, object]:
        manifest = self.package_manifest(tenant_id)
        key = SigningKey(publisher_id=tenant_id, secret=DEMO_SIGNING_SECRET)
        signature = PackageSignature.sign(manifest.manifest_hash(), key)
        return {
            "manifest": manifest.as_dict(),
            "manifest_hash": manifest.manifest_hash(),
            "signature": signature.signature,
            "fingerprint": signature.fingerprint,
            "metadata": self.package_metadata().as_dict(),
            "risk_summary": {
                "requires_approval": any(permission.startswith("network.") or permission.startswith("tenant.") for permission in self.tool_permissions),
                "raw_sensitive_persistence": False,
            },
            "install_example": {"package_id": self.package_id, "version": self.version, "approved_permissions": True},
            "rollback_example": {"package_id": self.package_id, "version": self.version, "admin_override": False},
        }


REFERENCE_AGENTS: tuple[ReferenceAgent, ...] = (
    ReferenceAgent(
        "research-agent",
        "ResearchAgent",
        "1.0.0",
        ("research", "retrieval"),
        ("tool.web.search", "memory.read"),
        {"question": "Summarize customer policy controls", "veil_reference": "veil-ref-demo"},
        {"summary": "Policy controls summarized with sources", "citations": ["doc://policy"]},
        "reference-research-agent",
        "Collects and summarizes safe research context.",
    ),
    ReferenceAgent(
        "document-analysis-agent",
        "DocumentAnalysisAgent",
        "1.0.0",
        ("analysis", "retrieval"),
        ("memory.read", "workflow.read"),
        {"document_ref": "veil-doc-ref", "task": "extract obligations"},
        {"obligations": ["retain audit logs", "enforce approvals"]},
        "reference-document-analysis-agent",
        "Analyzes tenant-visible document references.",
    ),
    ReferenceAgent(
        "compliance-review-agent",
        "ComplianceReviewAgent",
        "1.0.0",
        ("analysis", "review"),
        ("events.read", "audit.read"),
        {"workflow_id": "wf-demo", "framework": "SOC2"},
        {"status": "review_required", "findings": ["approval evidence required"]},
        "reference-compliance-review-agent",
        "Reviews workflow evidence against compliance expectations.",
    ),
    ReferenceAgent(
        "code-review-agent",
        "CodeReviewAgent",
        "1.0.0",
        ("coding", "review"),
        ("workflow.read", "events.read"),
        {"diff_ref": "veil-diff-ref", "focus": "security"},
        {"findings": ["no raw secret persistence"], "risk": "low"},
        "reference-code-review-agent",
        "Reviews code diffs and produces safe findings.",
    ),
    ReferenceAgent(
        "workflow-planner-agent",
        "WorkflowPlannerAgent",
        "1.0.0",
        ("planning",),
        ("workflow.start", "governance.propose"),
        {"goal": "review a document package"},
        {"nodes": ["research", "analysis", "review", "approval"]},
        "reference-workflow-planner-agent",
        "Plans governed multi-agent workflows.",
    ),
    ReferenceAgent(
        "human-approval-agent",
        "HumanApprovalAgent",
        "1.0.0",
        ("review",),
        ("governance.approve",),
        {"proposal_id": "proposal-demo", "reason": "pilot approval"},
        {"approved": True, "decision_record": "decision-demo"},
        "reference-human-approval-agent",
        "Bridges pilot workflows to human approvals.",
    ),
    ReferenceAgent(
        "marketplace-verifier-agent",
        "MarketplaceVerifierAgent",
        "1.0.0",
        ("analysis", "review"),
        ("marketplace.read", "events.read"),
        {"package_id": "reference-research-agent"},
        {"signature_verified": True, "risk": "low"},
        "reference-marketplace-verifier-agent",
        "Verifies signed package fixtures and marketplace risk summaries.",
    ),
)


def all_reference_agents() -> tuple[ReferenceAgent, ...]:
    return REFERENCE_AGENTS


def get_reference_agent(agent_id: str) -> ReferenceAgent:
    for agent in REFERENCE_AGENTS:
        if agent.agent_id == agent_id:
            return agent
    raise KeyError(agent_id)


def signed_package_fixtures(tenant_id: str = DEMO_TENANT_ID) -> list[dict[str, object]]:
    return [agent.signed_package_fixture(tenant_id) for agent in REFERENCE_AGENTS]
