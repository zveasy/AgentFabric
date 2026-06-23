"""Tenant audit bundle exporter."""

from __future__ import annotations

from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore

from .bundle import AuditBundle
from .manifest import AuditBundleManifest


class AuditBundleExporter:
    def __init__(self, *, persistence: PersistenceStore, event_store: EventStore) -> None:
        self.persistence = persistence
        self.event_store = event_store

    def export(self, tenant_id: str) -> AuditBundle:
        events = [event.as_dict() for event in self.event_store.replay() if event.payload.get("tenant_id") == tenant_id]
        event_ids = [event["event_id"] for event in events]
        decision_records = self.persistence.list_tenant("governance_decision_records", tenant_id)
        bundle = AuditBundle(
            manifest=AuditBundleManifest(tenant_id=tenant_id),
            tenant_summary={"tenant_id": tenant_id, "event_count": len(events)},
            workflow_timeline=[event for event in events if str(event["event_type"]).startswith(("workflow", "task", "checkpoint", "human_approval"))],
            decision_records=decision_records,
            package_installs=self.persistence.list_tenant("marketplace_installs", tenant_id),
            event_hash_chain={
                "valid": self.event_store.validate_integrity(),
                "first_event_id": event_ids[0] if event_ids else None,
                "last_event_id": event_ids[-1] if event_ids else None,
                "event_count": len(events),
            },
            veil_audit_references=_veil_refs(decision_records),
            reputation_summary={"records": self.persistence.list_tenant("reputation", tenant_id)},
            runtime_jobs=[item for item in self.persistence.list_tenant("runtime_jobs", tenant_id)],
            connectors=self.persistence.list_tenant("connectors", tenant_id),
            connector_results=self.persistence.list_tenant("connector_results", tenant_id),
            tools=self.persistence.list_tenant("tools", tenant_id),
            tool_results=self.persistence.list_tenant("tool_results", tenant_id),
            evaluation_results=self.persistence.list_tenant("evaluation_results", tenant_id),
            feedback=self.persistence.list_tenant("feedback", tenant_id),
            cost_events=self.persistence.list_tenant("cost_events", tenant_id),
            revenue_events=self.persistence.list_tenant("revenue_events", tenant_id),
            health_snapshots=self.persistence.list_tenant("agent_health_snapshots", tenant_id),
            drift_events=self.persistence.list_tenant("agent_drift_events", tenant_id),
            anomaly_events=self.persistence.list_tenant("agent_anomaly_records", tenant_id),
            recommendations=self.persistence.list_tenant("agent_recommendations", tenant_id),
            version_comparisons=self.persistence.list_tenant("agent_version_comparisons", tenant_id),
            connector_manifests=self.persistence.list_tenant("enterprise_connector_manifests", tenant_id),
            connector_enablement=self.persistence.list_tenant("enterprise_connector_enablement", tenant_id),
            connector_executions=self.persistence.list_tenant("enterprise_connector_executions", tenant_id),
            connector_denials=self.persistence.list_tenant("enterprise_connector_denials", tenant_id),
            credential_lifecycle=self.persistence.list_tenant("connector_credentials", tenant_id),
            connector_policies=self.persistence.list_tenant("enterprise_connector_policies", tenant_id),
            factory_ideas=self.persistence.list_tenant("factory_ideas", tenant_id),
            factory_repositories=self.persistence.list_tenant("factory_repositories", tenant_id),
            factory_platforms=self.persistence.list_tenant("factory_platforms", tenant_id),
            factory_artifacts=self.persistence.list_tenant("factory_artifacts", tenant_id),
            factory_packages=self.persistence.list_tenant("factory_repository_packages", tenant_id),
            factory_quality=self.persistence.list_tenant("factory_quality_scores", tenant_id),
            factory_tasks=self.persistence.list_tenant("factory_software_tasks", tenant_id),
            factory_execution_plans=_execution_plans(self.persistence, tenant_id),
            factory_execution_approvals=self.persistence.list_tenant("factory_execution_approvals", tenant_id),
            factory_execution_results=self.persistence.list_tenant("factory_execution_results", tenant_id),
            factory_execution_artifacts=self.persistence.list_tenant("factory_execution_artifacts", tenant_id),
            factory_execution_rollbacks=self.persistence.list_tenant("factory_execution_rollbacks", tenant_id),
            factory_build_plans=_build_plans(self.persistence, tenant_id),
            factory_build_approvals=self.persistence.list_tenant("factory_build_approvals", tenant_id),
            factory_build_results=self.persistence.list_tenant("factory_build_results", tenant_id),
            factory_build_artifacts=self.persistence.list_tenant("factory_build_artifacts", tenant_id),
            factory_build_reviews=self.persistence.list_tenant("factory_build_reviews", tenant_id),
            factory_build_rollbacks=self.persistence.list_tenant("factory_build_rollbacks", tenant_id),
            renovation_estimates=_renovation_artifacts(self.persistence, "renovation_estimates", tenant_id),
            renovation_proposals=_renovation_artifacts(self.persistence, "renovation_proposals", tenant_id),
            renovation_proposal_exports=self.persistence.list_tenant(
                "renovation_proposal_exports",
                tenant_id,
            ),
            renovation_jobs=_renovation_artifacts(self.persistence, "renovation_jobs", tenant_id),
            renovation_daily_logs=_renovation_artifacts(
                self.persistence,
                "renovation_daily_logs",
                tenant_id,
            ),
            renovation_field_notes=_renovation_artifacts(
                self.persistence,
                "renovation_field_notes",
                tenant_id,
            ),
            renovation_photo_records=_renovation_artifacts(
                self.persistence,
                "renovation_photo_records",
                tenant_id,
            ),
            renovation_issue_records=_renovation_artifacts(
                self.persistence,
                "renovation_issue_records",
                tenant_id,
            ),
            renovation_daily_summaries=self.persistence.list_tenant(
                "renovation_daily_summaries",
                tenant_id,
            ),
            renovation_change_orders=_renovation_artifacts(
                self.persistence,
                "renovation_change_orders",
                tenant_id,
            ),
            renovation_change_order_approvals=_renovation_artifacts(
                self.persistence,
                "renovation_change_order_approvals",
                tenant_id,
            ),
            renovation_change_order_exports=self.persistence.list_tenant(
                "renovation_change_order_exports",
                tenant_id,
            ),
            renovation_schedules=_renovation_artifacts(
                self.persistence,
                "renovation_schedules",
                tenant_id,
            ),
            renovation_schedule_recalculations=self.persistence.list_tenant(
                "renovation_schedule_recalculations",
                tenant_id,
            ),
            renovation_schedule_summaries=self.persistence.list_tenant(
                "renovation_schedule_summaries",
                tenant_id,
            ),
            renovation_crews=_renovation_artifacts(
                self.persistence,
                "renovation_crews",
                tenant_id,
            ),
            renovation_crew_assignments=_renovation_artifacts(
                self.persistence,
                "renovation_crew_assignments",
                tenant_id,
            ),
            renovation_crew_availability=_renovation_artifacts(
                self.persistence,
                "renovation_crew_availability",
                tenant_id,
            ),
            renovation_material_deliveries=_renovation_artifacts(
                self.persistence,
                "renovation_material_deliveries",
                tenant_id,
            ),
            renovation_delay_impacts=_renovation_artifacts(
                self.persistence,
                "renovation_delay_impacts",
                tenant_id,
            ),
            renovation_job_costs=_renovation_artifacts(
                self.persistence,
                "renovation_job_costs",
                tenant_id,
            ),
            renovation_invoices=_renovation_artifacts(
                self.persistence,
                "renovation_invoices",
                tenant_id,
            ),
            renovation_payments=_renovation_artifacts(
                self.persistence,
                "renovation_payments",
                tenant_id,
            ),
            renovation_payables=_renovation_artifacts(
                self.persistence,
                "renovation_payables",
                tenant_id,
            ),
            renovation_profitability_scorecards=_renovation_artifacts(
                self.persistence,
                "renovation_profitability_scorecards",
                tenant_id,
            ),
            renovation_margin_variances=_renovation_artifacts(
                self.persistence,
                "renovation_margin_variances",
                tenant_id,
            ),
            renovation_cost_overrun_alerts=_renovation_artifacts(
                self.persistence,
                "renovation_cost_overrun_alerts",
                tenant_id,
            ),
            renovation_cash_flow_forecasts=_renovation_artifacts(
                self.persistence,
                "renovation_cash_flow_forecasts",
                tenant_id,
            ),
            renovation_owner_summaries=self.persistence.list_tenant(
                "renovation_owner_summaries",
                tenant_id,
            ),
        )
        return bundle


def _veil_refs(records: list[dict[str, object]]) -> list[str]:
    refs: list[str] = []
    for record in records:
        refs.extend(str(item) for item in record.get("veil_audit_refs", ()))
    return refs


def _execution_plans(
    persistence: PersistenceStore,
    tenant_id: str,
) -> list[dict[str, object]]:
    plans = persistence.list_tenant("factory_execution_plans", tenant_id)
    for plan in plans:
        plan.pop("artifact_contents", None)
    return plans


def _build_plans(
    persistence: PersistenceStore,
    tenant_id: str,
) -> list[dict[str, object]]:
    plans = persistence.list_tenant("factory_build_plans", tenant_id)
    for plan in plans:
        plan.pop("artifact_contents", None)
    return plans


def _renovation_artifacts(
    persistence: PersistenceStore,
    collection: str,
    tenant_id: str,
) -> list[dict[str, object]]:
    return [
        {
            "tenant_id": item["tenant_id"],
            "organization_id": item["organization_id"],
            "created_by": item["created_by"],
            "artifact": item["artifact"],
        }
        for item in persistence.list_tenant(collection, tenant_id)
    ]
