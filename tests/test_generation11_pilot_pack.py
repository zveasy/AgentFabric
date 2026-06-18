from __future__ import annotations

import json
from pathlib import Path

from agentfabric.audit_bundle import contains_raw_sensitive, redact
from agentfabric.marketplace import SignatureVerifier, SigningKey, TrustedPublisherRegistry
from agentfabric.reference_agents import DEMO_SIGNING_SECRET, DEMO_TENANT_ID, all_reference_agents, signed_package_fixtures
from scripts.bootstrap_demo_tenant import bootstrap_demo_tenant
from scripts.run_demo_pilot import run_demo_pilot


ROOT = Path(__file__).resolve().parents[1]


def test_reference_agent_manifests_include_pilot_contract() -> None:
    agents = all_reference_agents()
    assert {agent.name for agent in agents} == {
        "ResearchAgent",
        "DocumentAnalysisAgent",
        "ComplianceReviewAgent",
        "CodeReviewAgent",
        "WorkflowPlannerAgent",
        "HumanApprovalAgent",
        "MarketplaceVerifierAgent",
    }
    for agent in agents:
        manifest = agent.manifest()
        assert manifest["agent_id"]
        assert manifest["capabilities"]
        assert manifest["tool_permissions"] is not None
        assert manifest["example_input"]
        assert manifest["example_output"]
        assert manifest["marketplace_package"]["package_id"] == agent.package_id
        agent.package_manifest().validate()


def test_package_signing_fixtures_verify_with_demo_key() -> None:
    key = SigningKey(publisher_id=DEMO_TENANT_ID, secret=DEMO_SIGNING_SECRET)
    trusted = TrustedPublisherRegistry()
    trusted.trust(DEMO_TENANT_ID, key.fingerprint)
    verifier = SignatureVerifier(trusted)

    fixtures = signed_package_fixtures()
    assert len(fixtures) == 7
    for fixture in fixtures:
        fingerprint = verifier.verify(
            publisher_id=DEMO_TENANT_ID,
            manifest_hash=str(fixture["manifest_hash"]),
            signature=str(fixture["signature"]),
            key=key,
        )
        assert fingerprint == fixture["fingerprint"]
        assert fixture["risk_summary"]["raw_sensitive_persistence"] is False


def test_demo_tenant_bootstrap_seeds_customer_pilot_state() -> None:
    summary = bootstrap_demo_tenant()
    assert summary["tenant"]["tenant_id"] == DEMO_TENANT_ID
    assert len(summary["reference_agents"]) == 7
    assert len(summary["installed_packages"]) == 7
    assert summary["governance"]["org"]["org_id"] == "gov-org-demo"
    assert summary["governance"]["team"]["team_id"] == "gov-team-demo-review"
    assert summary["billing"]["plan"] == "team"


def test_demo_pilot_runs_pause_resume_decision_and_audit_bundle() -> None:
    result = run_demo_pilot()
    assert result["workflow"]["paused"]["status"] == "awaiting_approval"
    assert result["workflow"]["resumed"]["status"] == "completed"
    assert result["governance"]["consensus"]["status"] == "approved"
    assert result["governance"]["decision_record"]["final_status"] == "executed"
    assert result["events"]["integrity_valid"] is True

    bundle = result["audit_bundle"]
    assert bundle["manifest"]["tenant_id"] == DEMO_TENANT_ID
    assert bundle["event_hash_chain"]["valid"] is True
    assert bundle["workflow_timeline"]
    assert bundle["decision_records"]
    assert bundle["package_installs"]
    assert bundle["runtime_jobs"]
    assert contains_raw_sensitive(bundle) is False


def test_audit_bundle_redacts_raw_sensitive_values() -> None:
    redacted = redact({"raw": "secret-value", "nested": [{"password": "secret-value"}, {"veil_reference": "veil-ref"}]})
    assert redacted["raw"] == "[REDACTED]"
    assert redacted["nested"][0]["password"] == "[REDACTED]"
    assert contains_raw_sensitive(redacted) is False


def test_marketplace_seed_examples_and_workflows_are_present() -> None:
    seed = json.loads((ROOT / "examples/marketplace/seed_packages.json").read_text(encoding="utf-8"))
    assert seed
    assert {"install_example", "rollback_example", "risk_summary"} <= set(seed[0])

    expected_workflows = {
        "document_review.json",
        "code_review.json",
        "compliance_review.json",
        "marketplace_package_approval.json",
        "federated_research_delegation.json",
        "human_approval_pause_resume.json",
        "recovery_after_restart.json",
    }
    workflow_dir = ROOT / "examples/workflows"
    assert expected_workflows <= {path.name for path in workflow_dir.glob("*.json")}
    for workflow_file in expected_workflows:
        workflow = json.loads((workflow_dir / workflow_file).read_text(encoding="utf-8"))
        assert "tenant context" in workflow["demonstrates"]
        assert "VEIL boundary usage" in workflow["demonstrates"]
        assert workflow["tenant_id"] == DEMO_TENANT_ID


def test_customer_docs_links_exist() -> None:
    docs = [
        ROOT / "docs/pilot/quickstart.md",
        ROOT / "docs/pilot/reference_agents.md",
        ROOT / "docs/pilot/demo_workflows.md",
        ROOT / "docs/pilot/marketplace_demo.md",
        ROOT / "docs/pilot/governance_demo.md",
        ROOT / "docs/pilot/audit_bundle.md",
        ROOT / "docs/pilot/faq.md",
    ]
    for doc in docs:
        assert doc.exists()
        text = doc.read_text(encoding="utf-8")
        assert "AgentFabric" in text or "Generation 11" in text or "pilot" in text.lower()

    assert (ROOT / "scripts/bootstrap_demo_tenant.py").exists()
    assert (ROOT / "scripts/run_demo_pilot.py").exists()
