"""Pilot audit bundle data model."""

from __future__ import annotations

from dataclasses import dataclass

from .manifest import AuditBundleManifest
from .redactor import contains_raw_sensitive, redact


@dataclass(frozen=True)
class AuditBundle:
    manifest: AuditBundleManifest
    tenant_summary: dict[str, object]
    workflow_timeline: list[dict[str, object]]
    decision_records: list[dict[str, object]]
    package_installs: list[dict[str, object]]
    event_hash_chain: dict[str, object]
    veil_audit_references: list[str]
    reputation_summary: dict[str, object]
    runtime_jobs: list[dict[str, object]]
    connectors: list[dict[str, object]]
    connector_results: list[dict[str, object]]
    tools: list[dict[str, object]]
    tool_results: list[dict[str, object]]
    evaluation_results: list[dict[str, object]]
    feedback: list[dict[str, object]]
    cost_events: list[dict[str, object]]
    revenue_events: list[dict[str, object]]
    health_snapshots: list[dict[str, object]]
    drift_events: list[dict[str, object]]
    anomaly_events: list[dict[str, object]]
    recommendations: list[dict[str, object]]
    version_comparisons: list[dict[str, object]]
    connector_manifests: list[dict[str, object]]
    connector_enablement: list[dict[str, object]]
    connector_executions: list[dict[str, object]]
    connector_denials: list[dict[str, object]]
    credential_lifecycle: list[dict[str, object]]
    connector_policies: list[dict[str, object]]
    factory_ideas: list[dict[str, object]]
    factory_repositories: list[dict[str, object]]
    factory_platforms: list[dict[str, object]]
    factory_artifacts: list[dict[str, object]]
    factory_packages: list[dict[str, object]]
    factory_quality: list[dict[str, object]]
    factory_tasks: list[dict[str, object]]
    factory_execution_plans: list[dict[str, object]]
    factory_execution_approvals: list[dict[str, object]]
    factory_execution_results: list[dict[str, object]]
    factory_execution_artifacts: list[dict[str, object]]
    factory_execution_rollbacks: list[dict[str, object]]
    factory_build_plans: list[dict[str, object]]
    factory_build_approvals: list[dict[str, object]]
    factory_build_results: list[dict[str, object]]
    factory_build_artifacts: list[dict[str, object]]
    factory_build_reviews: list[dict[str, object]]
    factory_build_rollbacks: list[dict[str, object]]
    renovation_estimates: list[dict[str, object]]
    renovation_proposals: list[dict[str, object]]
    renovation_proposal_exports: list[dict[str, object]]
    renovation_jobs: list[dict[str, object]]
    renovation_daily_logs: list[dict[str, object]]
    renovation_field_notes: list[dict[str, object]]
    renovation_photo_records: list[dict[str, object]]
    renovation_issue_records: list[dict[str, object]]
    renovation_daily_summaries: list[dict[str, object]]
    renovation_change_orders: list[dict[str, object]]
    renovation_change_order_approvals: list[dict[str, object]]
    renovation_change_order_exports: list[dict[str, object]]

    def as_dict(self) -> dict[str, object]:
        value = {
            "manifest": self.manifest.as_dict(),
            "tenant_summary": self.tenant_summary,
            "workflow_timeline": self.workflow_timeline,
            "decision_records": self.decision_records,
            "package_installs": self.package_installs,
            "event_hash_chain": self.event_hash_chain,
            "veil_audit_references": self.veil_audit_references,
            "reputation_summary": self.reputation_summary,
            "runtime_jobs": self.runtime_jobs,
            "connectors": self.connectors,
            "connector_results": self.connector_results,
            "tools": self.tools,
            "tool_results": self.tool_results,
            "evaluation_results": self.evaluation_results,
            "feedback": self.feedback,
            "cost_events": self.cost_events,
            "revenue_events": self.revenue_events,
            "health_snapshots": self.health_snapshots,
            "drift_events": self.drift_events,
            "anomaly_events": self.anomaly_events,
            "recommendations": self.recommendations,
            "version_comparisons": self.version_comparisons,
            "connector_manifests": self.connector_manifests,
            "connector_enablement": self.connector_enablement,
            "connector_executions": self.connector_executions,
            "connector_denials": self.connector_denials,
            "credential_lifecycle": self.credential_lifecycle,
            "connector_policies": self.connector_policies,
            "factory_ideas": self.factory_ideas,
            "factory_repositories": self.factory_repositories,
            "factory_platforms": self.factory_platforms,
            "factory_artifacts": self.factory_artifacts,
            "factory_packages": self.factory_packages,
            "factory_quality": self.factory_quality,
            "factory_tasks": self.factory_tasks,
            "factory_execution_plans": self.factory_execution_plans,
            "factory_execution_approvals": self.factory_execution_approvals,
            "factory_execution_results": self.factory_execution_results,
            "factory_execution_artifacts": self.factory_execution_artifacts,
            "factory_execution_rollbacks": self.factory_execution_rollbacks,
            "factory_build_plans": self.factory_build_plans,
            "factory_build_approvals": self.factory_build_approvals,
            "factory_build_results": self.factory_build_results,
            "factory_build_artifacts": self.factory_build_artifacts,
            "factory_build_reviews": self.factory_build_reviews,
            "factory_build_rollbacks": self.factory_build_rollbacks,
            "renovation_estimates": self.renovation_estimates,
            "renovation_proposals": self.renovation_proposals,
            "renovation_proposal_exports": self.renovation_proposal_exports,
            "renovation_jobs": self.renovation_jobs,
            "renovation_daily_logs": self.renovation_daily_logs,
            "renovation_field_notes": self.renovation_field_notes,
            "renovation_photo_records": self.renovation_photo_records,
            "renovation_issue_records": self.renovation_issue_records,
            "renovation_daily_summaries": self.renovation_daily_summaries,
            "renovation_change_orders": self.renovation_change_orders,
            "renovation_change_order_approvals": self.renovation_change_order_approvals,
            "renovation_change_order_exports": self.renovation_change_order_exports,
        }
        redacted = redact(value)
        if contains_raw_sensitive(redacted):
            raise ValueError("audit bundle contains raw sensitive values")
        return redacted
