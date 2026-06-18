"""Operational intelligence orchestration service."""

from __future__ import annotations

from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError, NotFoundError
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore

from .anomaly_detection import AnomalyDetector, AnomalyRecord
from .degradation_monitor import DegradationMonitor, DegradationRecord
from .drift_detection import DriftDetector, DriftEvent
from .health import HealthEngine, HealthSnapshot
from .metrics import AgentMetric
from .recommendation_engine import ImprovementRecommendation, RecommendationEngine
from .trend_analysis import TrendAnalyzer
from .version_comparison import VersionComparator, VersionComparison


class OperationalIntelligenceService:
    def __init__(self, persistence: PersistenceStore, event_store: EventStore) -> None:
        self.persistence = persistence
        self.event_store = event_store
        self.health_engine = HealthEngine()
        self.drift_detector = DriftDetector()
        self.anomaly_detector = AnomalyDetector()
        self.trends = TrendAnalyzer()
        self.comparator = VersionComparator()
        self.degradation_monitor = DegradationMonitor()
        self.recommendation_engine = RecommendationEngine()
        self.persistence.initialize()

    def record_metric(self, metric: AgentMetric) -> AgentMetric:
        metric.validate()
        self.persistence.put("agent_metrics", metric.metric_id, metric.as_dict())
        self.event_store.append("agent.metric.recorded", metric.agent_id, metric.as_dict())
        self.refresh(metric.tenant_id, metric.agent_id, metric.version)
        return metric

    def list_metrics(
        self,
        ctx: TenantContext,
        *,
        agent_id: str | None = None,
        version: str | None = None,
        metric: str | None = None,
    ) -> list[AgentMetric]:
        records = [AgentMetric.from_dict(item) for item in self.persistence.list_tenant("agent_metrics", ctx.tenant_id)]
        return [
            item for item in records
            if (agent_id is None or item.agent_id == agent_id)
            and (version is None or item.version == version)
            and (metric is None or item.metric == metric)
        ]

    def aggregate(self, ctx: TenantContext, *, agent_id: str | None = None, version: str | None = None) -> dict[str, object]:
        records = self.list_metrics(ctx, agent_id=agent_id, version=version)
        grouped: dict[str, list[float]] = {}
        for record in records:
            grouped.setdefault(record.metric, []).append(record.value)
        return {
            "count": len(records),
            "metrics": {
                name: {
                    "count": len(values),
                    "average": round(sum(values) / len(values), 4),
                    "minimum": min(values),
                    "maximum": max(values),
                }
                for name, values in sorted(grouped.items())
            },
        }

    def refresh(self, tenant_id: str, agent_id: str, version: str) -> HealthSnapshot:
        ctx = TenantContext(tenant_id, tenant_id, "observability-service", ())
        metrics = self.list_metrics(ctx, agent_id=agent_id, version=version)
        previous = self.latest_health(ctx, agent_id, version=version, required=False)
        health = self.health_engine.compute(tenant_id, agent_id, version, metrics)
        self.persistence.put("agent_health_snapshots", health.snapshot_id, health.as_dict())
        if previous is None or previous.status != health.status:
            self.event_store.append(
                "agent.health.changed",
                agent_id,
                {
                    **health.as_dict(),
                    "previous_status": previous.status if previous else None,
                },
            )

        drift = self.drift_detector.detect(metrics)
        existing_drift = {(item.metric, item.baseline, item.current_value) for item in self.list_drift(ctx, agent_id)}
        new_drift = [item for item in drift if (item.metric, item.baseline, item.current_value) not in existing_drift]
        for item in new_drift:
            self.persistence.put("agent_drift_events", item.drift_id, item.as_dict())
            self.event_store.append("agent.drift.detected", agent_id, item.as_dict())

        anomalies = self.anomaly_detector.detect(metrics)
        existing_anomalies = {(item.metric, item.expected_value, item.observed_value) for item in self.list_anomalies(ctx, agent_id)}
        new_anomalies = [
            item for item in anomalies
            if (item.metric, item.expected_value, item.observed_value) not in existing_anomalies
        ]
        for item in new_anomalies:
            self.persistence.put("agent_anomaly_records", item.anomaly_id, item.as_dict())
            self.event_store.append("agent.anomaly.detected", agent_id, item.as_dict())

        degradation = self.degradation_monitor.assess(health, drift)
        self.persistence.put("agent_degradations", f"{tenant_id}:{agent_id}:{version}", degradation.as_dict())
        if degradation.level != "none":
            self.event_store.append("agent.degradation.detected", agent_id, degradation.as_dict())

        recommendation = self.recommendation_engine.generate(health, degradation, drift, anomalies)
        latest = self.list_recommendations(ctx, agent_id)
        if not latest or latest[-1].recommendation_type != recommendation.recommendation_type or latest[-1].version != version:
            self.persistence.put("agent_recommendations", recommendation.recommendation_id, recommendation.as_dict())
            self.event_store.append("agent.recommendation.created", agent_id, recommendation.as_dict())
        return health

    def latest_health(
        self,
        ctx: TenantContext,
        agent_id: str,
        *,
        version: str | None = None,
        required: bool = True,
    ) -> HealthSnapshot | None:
        records = self.health_history(ctx, agent_id, version=version)
        if not records:
            if required:
                raise NotFoundError("agent health not found")
            return None
        return records[-1]

    def health_history(self, ctx: TenantContext, agent_id: str, *, version: str | None = None) -> list[HealthSnapshot]:
        records = [
            HealthSnapshot.from_dict(item)
            for item in self.persistence.list_tenant("agent_health_snapshots", ctx.tenant_id)
            if item.get("agent_id") == agent_id and (version is None or item.get("version") == version)
        ]
        return sorted(records, key=lambda item: item.timestamp)

    def list_drift(self, ctx: TenantContext, agent_id: str) -> list[DriftEvent]:
        return [
            DriftEvent.from_dict(item)
            for item in self.persistence.list_tenant("agent_drift_events", ctx.tenant_id)
            if item.get("agent_id") == agent_id
        ]

    def list_anomalies(self, ctx: TenantContext, agent_id: str) -> list[AnomalyRecord]:
        return [
            AnomalyRecord.from_dict(item)
            for item in self.persistence.list_tenant("agent_anomaly_records", ctx.tenant_id)
            if item.get("agent_id") == agent_id
        ]

    def latest_degradation(self, ctx: TenantContext, agent_id: str, *, version: str | None = None) -> DegradationRecord | None:
        records = [
            DegradationRecord.from_dict(item)
            for item in self.persistence.list_tenant("agent_degradations", ctx.tenant_id)
            if item.get("agent_id") == agent_id and (version is None or item.get("version") == version)
        ]
        return sorted(records, key=lambda item: item.timestamp)[-1] if records else None

    def list_recommendations(self, ctx: TenantContext, agent_id: str) -> list[ImprovementRecommendation]:
        records = [
            ImprovementRecommendation.from_dict(item)
            for item in self.persistence.list_tenant("agent_recommendations", ctx.tenant_id)
            if item.get("agent_id") == agent_id
        ]
        return sorted(records, key=lambda item: item.created_at)

    def approve_recommendation(self, ctx: TenantContext, agent_id: str, recommendation_id: str) -> ImprovementRecommendation:
        item = self.persistence.get("agent_recommendations", recommendation_id)
        if item is None:
            raise NotFoundError("recommendation not found")
        recommendation = ImprovementRecommendation.from_dict(item)
        if recommendation.tenant_id != ctx.tenant_id or recommendation.agent_id != agent_id:
            raise AuthorizationError("cross-tenant recommendation access denied")
        approved = recommendation.approve(ctx.principal_id)
        self.persistence.put("agent_recommendations", approved.recommendation_id, approved.as_dict())
        return approved

    def compare_versions(
        self,
        ctx: TenantContext,
        agent_id: str,
        baseline_version: str,
        candidate_version: str,
    ) -> VersionComparison:
        comparison = self.comparator.compare(
            tenant_id=ctx.tenant_id,
            agent_id=agent_id,
            baseline_version=baseline_version,
            candidate_version=candidate_version,
            metrics=self.list_metrics(ctx, agent_id=agent_id),
        )
        self.persistence.put("agent_version_comparisons", comparison.comparison_id, comparison.as_dict())
        self.event_store.append("agent.version.compared", agent_id, comparison.as_dict())
        return comparison

    def enforce_marketplace_gate(self, ctx: TenantContext, agent_id: str, version: str, minimum_quality: float = 0.8) -> None:
        health = self.latest_health(ctx, agent_id, version=version, required=False)
        if health is None:
            return
        degradation = self.latest_degradation(ctx, agent_id, version=version)
        if health.status == "critical":
            raise AuthorizationError("marketplace publication blocked: agent health is critical")
        if degradation and degradation.level in {"major", "critical"}:
            raise AuthorizationError(f"marketplace publication blocked: degradation is {degradation.level}")
        if health.dimensions.get("quality", 0.0) < minimum_quality:
            raise AuthorizationError("marketplace publication blocked: quality threshold not met")
