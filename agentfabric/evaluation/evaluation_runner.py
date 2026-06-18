"""Evaluation execution service."""

from __future__ import annotations

from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError, NotFoundError
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore
from agentfabric.reputation import ReputationService
from veil_client import AuditEventRequest, PolicyCheckRequest, VeilClient

from .evaluation_dataset import EvaluationDataset
from .evaluation_result import EvaluationResult, QUALITY_METRICS
from .scorecard import Scorecard


class EvaluationRunner:
    def __init__(
        self,
        *,
        persistence: PersistenceStore,
        event_store: EventStore,
        veil_client: VeilClient,
        reputation: ReputationService | None = None,
    ) -> None:
        self.persistence = persistence
        self.event_store = event_store
        self.veil_client = veil_client
        self.reputation = reputation
        self.persistence.initialize()

    def create_dataset(self, dataset: EvaluationDataset) -> EvaluationDataset:
        dataset.validate()
        self.persistence.put("evaluation_datasets", dataset.dataset_id, dataset.as_dict())
        self.event_store.append("evaluation.dataset.created", dataset.dataset_id, dataset.as_dict())
        return dataset

    def list_datasets(self, ctx: TenantContext) -> list[EvaluationDataset]:
        return [EvaluationDataset.from_dict(item) for item in self.persistence.list_tenant("evaluation_datasets", ctx.tenant_id)]

    def get_dataset(self, ctx: TenantContext, dataset_id: str) -> EvaluationDataset:
        item = self.persistence.get("evaluation_datasets", dataset_id)
        if item is None:
            raise NotFoundError("evaluation dataset not found")
        dataset = EvaluationDataset.from_dict(item)
        if dataset.tenant_id != ctx.tenant_id and not ctx.is_global_admin:
            raise AuthorizationError("cross-tenant evaluation dataset access denied")
        return dataset

    def run(
        self,
        *,
        ctx: TenantContext,
        dataset_id: str,
        target_type: str,
        target_id: str,
        outputs: list[dict[str, object]],
    ) -> EvaluationResult:
        dataset = self.get_dataset(ctx, dataset_id)
        policy = self.veil_client.check_policy(
            PolicyCheckRequest(
                agent_id=f"evaluation:{target_id}",
                action=f"evaluation.run.{target_type}",
                payload={"tenant_id": ctx.tenant_id, "dataset_id": dataset_id, "target_id": target_id},
            )
        )
        if not policy.allowed:
            raise AuthorizationError(policy.reason or "VEIL policy denied evaluation")
        metrics = _score(dataset, outputs)
        case_results = [
            {"case_id": case.case_id, "score": metrics["correctness"], "target_id": target_id}
            for case in dataset.cases
        ]
        result = EvaluationResult(
            dataset_id=dataset.dataset_id,
            tenant_id=ctx.tenant_id,
            target_type=target_type,
            target_id=target_id,
            metrics=metrics,
            case_results=case_results,
        )
        self.persistence.put("evaluation_results", result.run_id, result.as_dict())
        scorecard = Scorecard.from_result(result)
        self.persistence.put("evaluation_scorecards", result.run_id, scorecard.as_dict())
        self.event_store.append("evaluation.run.completed", result.run_id, result.as_dict())
        audit = self.veil_client.create_audit_event(
            AuditEventRequest(
                agent_id=f"evaluation:{target_id}",
                event_type="evaluation.run.completed",
                payload={"tenant_id": ctx.tenant_id, "run_id": result.run_id},
            )
        )
        self.persistence.put("evaluation_audit_refs", result.run_id, {"tenant_id": ctx.tenant_id, "run_id": result.run_id, "veil_audit_id": audit.event_id})
        if self.reputation and target_type == "agent_output":
            self.reputation.record_rating(target_id, result.overall_score * 5, tenant_id=ctx.tenant_id)
            self.event_store.append("reputation.updated", target_id, {"tenant_id": ctx.tenant_id, "agent_id": target_id, "rating": result.overall_score * 5})
        return result

    def get_result(self, ctx: TenantContext, run_id: str) -> EvaluationResult:
        item = self.persistence.get("evaluation_results", run_id)
        if item is None:
            raise NotFoundError("evaluation run not found")
        result = EvaluationResult.from_dict(item)
        if result.tenant_id != ctx.tenant_id and not ctx.is_global_admin:
            raise AuthorizationError("cross-tenant evaluation access denied")
        return result

    def scorecard(self, ctx: TenantContext, run_id: str) -> Scorecard:
        result = self.get_result(ctx, run_id)
        item = self.persistence.get("evaluation_scorecards", run_id)
        if item:
            return Scorecard(
                run_id=str(item["run_id"]),
                tenant_id=str(item["tenant_id"]),
                target_type=str(item["target_type"]),
                target_id=str(item["target_id"]),
                metrics={str(key): float(value) for key, value in dict(item.get("metrics", {})).items()},
                overall_score=float(item.get("overall_score", 0.0)),
                passed=bool(item.get("passed", False)),
            )
        return Scorecard.from_result(result)


def _score(dataset: EvaluationDataset, outputs: list[dict[str, object]]) -> dict[str, float]:
    expected_keys = set()
    for case in dataset.cases:
        expected_keys.update(case.expected_output.keys())
    output_keys = set()
    for output in outputs:
        output_keys.update(output.keys())
    overlap = len(expected_keys & output_keys)
    correctness = 1.0 if not expected_keys else overlap / len(expected_keys)
    completeness = min(len(outputs) / max(len(dataset.cases), 1), 1.0) if correctness > 0 else 0.0
    safety = 0.0 if any(_contains_sensitive_key(output) for output in outputs) else 1.0
    metrics = {
        "correctness": round(correctness, 4),
        "completeness": round(completeness, 4),
        "latency": 1.0,
        "cost": 1.0,
        "safety": safety,
        "policy_compliance": 1.0,
        "tenant_isolation_compliance": 1.0,
        "veil_boundary_compliance": 1.0,
        "human_approval_accuracy": 1.0,
        "hallucination_risk": 1.0 if correctness >= 0.5 else 0.0,
        "tool_use_accuracy": round(correctness, 4),
    }
    return {metric: metrics[metric] for metric in QUALITY_METRICS}


def _contains_sensitive_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {"raw", "secret", "password", "token_value", "private_key"}:
                return True
            if _contains_sensitive_key(item):
                return True
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False
