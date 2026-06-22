"""Approval-gated, replayable repository execution engine."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError, NotFoundError
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore
from agentfabric.repository_materializer import RenovationRepositorySpec, RepositoryMaterializer

from .approval_gate import ApprovalGate, ApprovalRecord
from .artifact_writer import ArtifactWriter, validate_relative_path
from .dry_run import DryRunResult
from .execution_context import ExecutionContext
from .execution_plan import ExecutionPlan
from .execution_result import ExecutionResult
from .execution_step import ExecutionStep


RENOVATION_MODELS = {
    "reno_estimator": (
        "ProjectIntake",
        "RoomScope",
        "MaterialSelection",
        "LaborAssumption",
        "EstimateLineItem",
        "EstimateResult",
        "MarginScenario",
        "RiskAdjustment",
    ),
    "change_order_agent": (
        "ChangeOrder",
        "ScopeDelta",
        "CostDelta",
        "ScheduleDelta",
        "ApprovalStatus",
        "CustomerApproval",
        "ContractorAcknowledgement",
        "ChangeOrderAuditRecord",
    ),
    "contractor_command_center": (
        "ContractorProfile",
        "CrewAssignment",
        "JobTask",
        "AttendanceRecord",
        "QualityIssue",
        "LicenseDocument",
        "InsuranceDocument",
        "PaymentMilestone",
    ),
}

PURPOSES = {
    "reno_estimator": "Produce auditable renovation estimates, margins, and risk adjustments.",
    "change_order_agent": "Govern renovation scope, cost, schedule, and approval changes.",
    "contractor_command_center": "Coordinate contractors, crews, quality, compliance, and milestones.",
}

RENOVATION_DEPENDENCIES = {
    "reno_estimator": (),
    "change_order_agent": ("reno_estimator",),
    "contractor_command_center": ("change_order_agent", "materials_intelligence"),
}


class RepositoryExecutionEngine:
    def __init__(
        self,
        persistence: PersistenceStore,
        event_store: EventStore,
        output_root: Path,
        platform_root: Path,
        tenant_subdirectories: bool = True,
    ) -> None:
        self.persistence = persistence
        self.event_store = event_store
        self.output_root = output_root
        self.platform_root = platform_root
        self.tenant_subdirectories = tenant_subdirectories
        self.materializer = RepositoryMaterializer()
        self.writer = ArtifactWriter(output_root)
        self.approvals = ApprovalGate(persistence)

    def plan(
        self,
        ctx: TenantContext,
        repository_name: str,
        *,
        platform_id: str = "RenovationOS",
        blueprint_version: str = "1.0.0",
        knowledge_pack_version: str = "1.0.0",
    ) -> ExecutionPlan:
        spec = self._spec(repository_name, platform_id)
        files = self.materializer.materialize(spec)
        gates = self._quality_gates(spec, files)
        if not all(gates.values()):
            raise ValueError("repository execution quality gates failed")
        artifact_hashes = {path: sha256(content.encode()).hexdigest() for path, content in files.items()}
        identity = {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "platform_id": platform_id,
            "repository_id": repository_name,
            "blueprint_version": blueprint_version,
            "knowledge_pack_version": knowledge_pack_version,
            "artifact_hashes": artifact_hashes,
        }
        execution_id = f"exec-{_digest(identity)[:20]}"
        context = ExecutionContext(
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
            principal_id=ctx.principal_id,
            platform_id=platform_id,
            repository_id=repository_name,
            blueprint_version=blueprint_version,
            knowledge_pack_version=knowledge_pack_version,
        )
        steps = tuple(
            ExecutionStep(
                step_id=f"{execution_id}:{index:03d}",
                order=index,
                action="write",
                target=path,
                content_hash=artifact_hashes[path],
            )
            for index, path in enumerate(sorted(files), start=1)
        )
        marketplace_metadata = {
            "private": True,
            "platform": platform_id,
            "industry": "construction",
            "capability": repository_name,
            "dependencies": sorted(spec.dependencies),
            "quality_score": 1.0,
            "release_readiness": "candidate",
        }
        plan = ExecutionPlan(
            execution_id=execution_id,
            context=context,
            steps=steps,
            artifact_contents=files,
            artifact_hashes=artifact_hashes,
            quality_gates=gates,
            rollback_plan=tuple(sorted(files)),
            marketplace_metadata=marketplace_metadata,
        )
        self.persistence.put("factory_execution_plans", execution_id, plan.as_dict(include_contents=True))
        self._event("factory.execution.planned", plan, {"plan_digest": plan.digest})
        return plan

    def dry_run(self, ctx: TenantContext, execution_id: str) -> DryRunResult:
        plan = self.get(ctx, execution_id)
        replayed = self.materializer.materialize(self._spec(plan.context.repository_id, plan.context.platform_id))
        stable = replayed == plan.artifact_contents
        gates = {**plan.quality_gates, "deterministic_replay": stable}
        if not all(gates.values()):
            raise ValueError("repository dry-run quality gates failed")
        result = DryRunResult(
            execution_id=execution_id,
            tenant_id=ctx.tenant_id,
            status="dry_run_complete",
            artifact_count=len(plan.steps),
            artifact_hashes=plan.artifact_hashes,
            quality_gates=gates,
        )
        self.persistence.put("factory_execution_dry_runs", execution_id, result.as_dict())
        self._event("factory.execution.dry_run.completed", plan, result.as_dict())
        return result

    def approve(self, ctx: TenantContext, execution_id: str) -> ApprovalRecord:
        plan = self.get(ctx, execution_id)
        approval = self.approvals.approve(execution_id, ctx.tenant_id, ctx.principal_id, plan.digest)
        self._event("factory.execution.approval.recorded", plan, approval.as_dict())
        return approval

    def execute(self, ctx: TenantContext, execution_id: str) -> ExecutionResult:
        plan = self.get(ctx, execution_id)
        existing = self.persistence.get("factory_execution_results", execution_id)
        if existing and existing.get("status") == "completed":
            return _result_from_dict(existing)
        approval = self.approvals.require(execution_id, ctx.tenant_id, plan.digest)
        for step in plan.steps:
            self._event("factory.execution.step.started", plan, step.as_dict())
        try:
            hashes = self.writer.write(self._destination(plan), plan.artifact_contents)
            if hashes != plan.artifact_hashes:
                raise ValueError("written artifact hashes do not match approved plan")
        except Exception as exc:
            self._event("factory.execution.step.failed", plan, {"reason": str(exc)})
            raise
        for step in plan.steps:
            self._event("factory.execution.step.completed", plan, step.as_dict())
        result = ExecutionResult(
            execution_id=execution_id,
            tenant_id=ctx.tenant_id,
            status="completed",
            artifact_hashes=hashes,
            approval=approval.as_dict(),
            rollback_plan=plan.rollback_plan,
            marketplace_metadata=plan.marketplace_metadata,
        )
        self.persistence.put("factory_execution_results", execution_id, result.as_dict())
        self.persistence.put(
            "factory_execution_marketplace_metadata",
            execution_id,
            {"tenant_id": ctx.tenant_id, "execution_id": execution_id, **plan.marketplace_metadata},
        )
        for path, digest in hashes.items():
            self.persistence.put(
                "factory_execution_artifacts",
                f"{execution_id}:{path}",
                {
                    "tenant_id": ctx.tenant_id,
                    "execution_id": execution_id,
                    "path": path,
                    "sha256": digest,
                },
            )
        self._event("factory.execution.completed", plan, result.as_dict())
        return result

    def replay(self, ctx: TenantContext, execution_id: str) -> ExecutionPlan:
        plan = self.get(ctx, execution_id)
        replayed = self.plan(
            ctx,
            plan.context.repository_id,
            platform_id=plan.context.platform_id,
            blueprint_version=plan.context.blueprint_version,
            knowledge_pack_version=plan.context.knowledge_pack_version,
        )
        if replayed.execution_id != execution_id or replayed.artifact_hashes != plan.artifact_hashes:
            raise ValueError("repository execution replay diverged")
        self._event("factory.execution.replayed", plan, {"plan_digest": replayed.digest})
        return replayed

    def rollback(self, ctx: TenantContext, execution_id: str) -> dict[str, object]:
        plan = self.get(ctx, execution_id)
        self.approvals.require(execution_id, ctx.tenant_id, plan.digest)
        removed = self.writer.rollback(self._destination(plan), plan.rollback_plan)
        value = {
            "tenant_id": ctx.tenant_id,
            "execution_id": execution_id,
            "status": "rolled_back",
            "removed": removed,
        }
        self.persistence.put("factory_execution_rollbacks", execution_id, value)
        self._event("factory.execution.rolled_back", plan, value)
        return value

    def get(self, ctx: TenantContext, execution_id: str) -> ExecutionPlan:
        value = self.persistence.get("factory_execution_plans", execution_id)
        if value is None:
            raise NotFoundError("repository execution not found")
        if value.get("tenant_id") != ctx.tenant_id:
            raise AuthorizationError("cross-tenant repository execution access denied")
        return _plan_from_dict(value)

    def events(self, ctx: TenantContext, execution_id: str) -> list[dict[str, object]]:
        self.get(ctx, execution_id)
        return [event.as_dict() for event in self.event_store.replay(execution_id)]

    def artifacts(self, ctx: TenantContext, execution_id: str) -> list[dict[str, object]]:
        self.get(ctx, execution_id)
        return [
            item
            for item in self.persistence.list_tenant("factory_execution_artifacts", ctx.tenant_id)
            if item.get("execution_id") == execution_id
        ]

    def _spec(self, repository_name: str, platform_id: str) -> RenovationRepositorySpec:
        if platform_id != "RenovationOS":
            raise NotFoundError("only RenovationOS execution is available in Generation 18")
        if repository_name not in RENOVATION_MODELS:
            raise NotFoundError("RenovationOS repository definition not found")
        manifest_path = self.platform_root / f"{repository_name}.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        return RenovationRepositorySpec(
            name=repository_name,
            repository_type=str(payload["type"]),
            purpose=PURPOSES[repository_name],
            models=RENOVATION_MODELS[repository_name],
            apis=tuple(str(item) for item in payload["apis"]),
            events=tuple(str(item) for item in payload["events"]),
            rbac_scopes=tuple(str(item) for item in payload["rbac_scopes"]),
            metrics=tuple(str(item) for item in payload["metrics"]),
            tests=tuple(str(item) for item in payload["tests"]),
            deployment_requirements=tuple(str(item) for item in payload["deployment_requirements"]),
            dependencies=RENOVATION_DEPENDENCIES[repository_name],
        )

    def _quality_gates(
        self,
        spec: RenovationRepositorySpec,
        files: dict[str, str],
    ) -> dict[str, bool]:
        for path in files:
            validate_relative_path(path)
        manifest = spec.manifest()
        required_files = {
            "README.md",
            "docs/architecture.md",
            "docs/api.md",
            "docs/deployment.md",
            "pyproject.toml",
            "repository.manifest.json",
            "tests/test_models.py",
        }
        replay = self.materializer.materialize(spec)
        return {
            "repository_name_safe": bool(spec.name),
            "path_safety": all(".." not in path for path in files),
            "template_valid": all(isinstance(content, str) and content for content in files.values()),
            "manifest_complete": all(manifest.get(key) for key in ("name", "domain", "purpose", "architecture")),
            "dependency_graph_consistent": spec.name not in spec.dependencies,
            "rbac_scopes_declared": bool(spec.rbac_scopes),
            "event_schemas_declared": bool(spec.events),
            "documentation_present": required_files <= set(files),
            "tests_present": any(path.startswith("tests/") for path in files),
            "deterministic_export_stable": replay == files,
        }

    def _event(self, event_type: str, plan: ExecutionPlan, payload: dict[str, object]) -> None:
        self.event_store.append(
            event_type,
            plan.execution_id,
            {
                "tenant_id": plan.context.tenant_id,
                "platform_id": plan.context.platform_id,
                "repository_id": plan.context.repository_id,
                **payload,
            },
        )

    def _destination(self, plan: ExecutionPlan) -> str:
        if self.tenant_subdirectories:
            return f"{plan.context.tenant_id}/{plan.context.repository_id}"
        return plan.context.repository_id


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _plan_from_dict(value: dict[str, object]) -> ExecutionPlan:
    context = ExecutionContext(**{key: str(item) for key, item in dict(value["context"]).items()})
    return ExecutionPlan(
        execution_id=str(value["execution_id"]),
        context=context,
        steps=tuple(
            ExecutionStep(
                step_id=str(item["step_id"]),
                order=int(item["order"]),
                action=str(item["action"]),
                target=str(item["target"]),
                content_hash=str(item["content_hash"]),
            )
            for item in value["steps"]
        ),
        artifact_contents={str(key): str(item) for key, item in dict(value["artifact_contents"]).items()},
        artifact_hashes={str(key): str(item) for key, item in dict(value["artifact_hashes"]).items()},
        quality_gates={str(key): bool(item) for key, item in dict(value["quality_gates"]).items()},
        rollback_plan=tuple(str(item) for item in value["rollback_plan"]),
        marketplace_metadata=dict(value["marketplace_metadata"]),
        status=str(value.get("status", "planned")),
    )


def _result_from_dict(value: dict[str, object]) -> ExecutionResult:
    return ExecutionResult(
        execution_id=str(value["execution_id"]),
        tenant_id=str(value["tenant_id"]),
        status=str(value["status"]),
        artifact_hashes={str(key): str(item) for key, item in dict(value["artifact_hashes"]).items()},
        approval=dict(value["approval"]),
        rollback_plan=tuple(str(item) for item in value["rollback_plan"]),
        marketplace_metadata=dict(value["marketplace_metadata"]),
    )
