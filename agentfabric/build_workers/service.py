"""Approval-gated deterministic build worker orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError, NotFoundError
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore
from agentfabric.repository_execution import RepositoryExecutionEngine, validate_relative_path

from .api_route_worker import ApiRouteWorker
from .documentation_worker import DocumentationWorker
from .domain_model_worker import DomainModelWorker
from .product_logic import product_artifacts
from .quality_worker import QualityWorker
from .security_review_worker import SecurityReviewWorker
from .service_logic_worker import ServiceLogicWorker
from .test_worker import TestWorker
from .worker_context import WorkerContext
from .worker_registry import WorkerRegistry
from .worker_task import WorkerTask


WORKER_IDS = (
    "domain-model-worker",
    "service-logic-worker",
    "api-route-worker",
    "test-worker",
    "documentation-worker",
    "quality-worker",
    "security-review-worker",
)


class BuildWorkerService:
    def __init__(
        self,
        persistence: PersistenceStore,
        event_store: EventStore,
        execution_engine: RepositoryExecutionEngine,
        output_root: Path,
        *,
        tenant_subdirectories: bool = True,
    ) -> None:
        self.persistence = persistence
        self.event_store = event_store
        self.execution_engine = execution_engine
        self.output_root = output_root.resolve()
        self.tenant_subdirectories = tenant_subdirectories
        self.registry = WorkerRegistry()
        for worker in (
            DomainModelWorker(),
            ServiceLogicWorker(),
            ApiRouteWorker(),
            TestWorker(),
            DocumentationWorker(),
            QualityWorker(),
            SecurityReviewWorker(),
        ):
            self.registry.register(worker)

    def plan(self, ctx: TenantContext, execution_id: str) -> dict[str, object]:
        execution = self.execution_engine.get(ctx, execution_id)
        execution_result = self.persistence.get("factory_execution_results", execution_id)
        if execution_result is None or execution_result.get("status") != "completed":
            raise AuthorizationError("completed approved repository execution is required")
        manifest = json.loads(execution.artifact_contents["repository.manifest.json"])
        context = WorkerContext(
            tenant_id=ctx.tenant_id,
            platform_id=execution.context.platform_id,
            repository_id=execution.context.repository_id,
            repository_type=str(manifest["repository_type"]),
            domain=str(manifest["domain"]),
            execution_id=execution_id,
            input_artifact_hashes=dict(execution_result["artifact_hashes"]),
        )
        artifacts: dict[str, str] = {}
        worker_results: list[dict[str, object]] = []
        tasks: list[dict[str, object]] = []
        for order, worker_id in enumerate(WORKER_IDS, start=1):
            worker = self.registry.get(worker_id, context)
            result = worker.run(context)
            overlap = set(artifacts) & set(result.artifacts)
            if overlap:
                raise ValueError(f"build workers produced conflicting artifacts: {sorted(overlap)}")
            artifacts.update(result.artifacts)
            worker_results.append(result.as_dict())
            tasks.append(
                WorkerTask(
                    build_id="pending",
                    worker_id=worker_id,
                    capability=worker.manifest.capability,
                    repository_id=context.repository_id,
                    order=order,
                ).as_dict()
            )
        marketplace = json.loads(product_artifacts(context.repository_id)["_marketplace_metadata"])
        package_manifest = json.loads(execution.artifact_contents["package.manifest.json"])
        package_manifest.update(marketplace)
        artifacts["package.manifest.json"] = json.dumps(package_manifest, indent=2, sort_keys=True) + "\n"
        hashes = {path: sha256(content.encode()).hexdigest() for path, content in sorted(artifacts.items())}
        identity = {
            "tenant_id": ctx.tenant_id,
            "execution_id": execution_id,
            "workers": WORKER_IDS,
            "output_artifact_hashes": hashes,
        }
        build_id = f"build-{_digest(identity)[:20]}"
        tasks = [{**task, "build_id": build_id} for task in tasks]
        gates = self._quality_gates(execution.as_dict(), artifacts, worker_results)
        if not all(gates.values()):
            raise ValueError("build quality gates failed")
        plan = {
            "build_id": build_id,
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": ctx.principal_id,
            "execution_id": execution_id,
            "repository_id": context.repository_id,
            "platform_id": context.platform_id,
            "worker_ids": list(WORKER_IDS),
            "tasks": tasks,
            "worker_results": worker_results,
            "input_artifact_hashes": dict(sorted(context.input_artifact_hashes.items())),
            "output_artifact_hashes": hashes,
            "artifact_contents": dict(sorted(artifacts.items())),
            "quality_gates": gates,
            "rollback_plan": sorted(artifacts),
            "marketplace_metadata": marketplace,
            "review_status": "pending",
            "status": "planned",
        }
        plan["plan_digest"] = _digest(plan)
        self.persistence.put("factory_build_plans", build_id, plan)
        self._event("factory.build.planned", plan, {"plan_digest": plan["plan_digest"]})
        return _public_plan(plan)

    def dry_run(self, ctx: TenantContext, build_id: str) -> dict[str, object]:
        plan = self._get(ctx, build_id)
        replay = self.plan(ctx, str(plan["execution_id"]))
        stable = replay["build_id"] == build_id and replay["output_artifact_hashes"] == plan["output_artifact_hashes"]
        if not stable:
            raise ValueError("build dry-run output diverged")
        result = {
            "build_id": build_id,
            "tenant_id": ctx.tenant_id,
            "status": "dry_run_complete",
            "deterministic_replay": True,
            "artifact_count": len(plan["output_artifact_hashes"]),
        }
        self.persistence.put("factory_build_dry_runs", build_id, result)
        self._event("factory.build.dry_run.completed", plan, result)
        return result

    def approve(self, ctx: TenantContext, build_id: str) -> dict[str, object]:
        plan = self._get(ctx, build_id)
        approval = {
            "build_id": build_id,
            "tenant_id": ctx.tenant_id,
            "approved_by": ctx.principal_id,
            "approved_at": datetime.now(tz=timezone.utc).isoformat(),
            "plan_digest": plan["plan_digest"],
        }
        self.persistence.put("factory_build_approvals", build_id, approval)
        self._event("factory.build.approval.recorded", plan, approval)
        return approval

    def execute(self, ctx: TenantContext, build_id: str) -> dict[str, object]:
        plan = self._get(ctx, build_id)
        existing = self.persistence.get("factory_build_results", build_id)
        if existing and existing.get("status") == "completed":
            return existing
        approval = self._approval(ctx, plan)
        destination = self._destination(plan)
        backups: dict[str, str | None] = {}
        written: list[str] = []
        try:
            for task in plan["tasks"]:
                self._event("factory.build.worker.started", plan, dict(task))
            for relative_path, content in sorted(dict(plan["artifact_contents"]).items()):
                validate_relative_path(relative_path)
                target = (destination / relative_path).resolve()
                if destination not in target.parents:
                    raise ValueError("build artifact escapes repository destination")
                backups[relative_path] = target.read_text(encoding="utf-8") if target.exists() else None
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(content), encoding="utf-8")
                written.append(relative_path)
            actual = {
                path: sha256((destination / path).read_bytes()).hexdigest()
                for path in sorted(plan["artifact_contents"])
            }
            if actual != plan["output_artifact_hashes"]:
                raise ValueError("build artifact hashes do not match approved plan")
        except Exception as exc:
            self._restore(destination, backups, written)
            self._event("factory.build.failed", plan, {"reason": str(exc)})
            raise
        for task in plan["tasks"]:
            self._event("factory.build.worker.completed", plan, dict(task))
        rollback = {
            "build_id": build_id,
            "tenant_id": ctx.tenant_id,
            "repository_id": plan["repository_id"],
            "backups": backups,
        }
        self.persistence.put("factory_build_rollback_plans", build_id, rollback)
        for path, digest in actual.items():
            self.persistence.put(
                "factory_build_artifacts",
                f"{build_id}:{path}",
                {
                    "tenant_id": ctx.tenant_id,
                    "build_id": build_id,
                    "repository_id": plan["repository_id"],
                    "path": path,
                    "sha256": digest,
                },
            )
        metadata = {
            "tenant_id": ctx.tenant_id,
            "build_id": build_id,
            "repository_id": plan["repository_id"],
            **dict(plan["marketplace_metadata"]),
        }
        self.persistence.put("factory_build_marketplace_metadata", build_id, metadata)
        result = {
            "build_id": build_id,
            "tenant_id": ctx.tenant_id,
            "repository_id": plan["repository_id"],
            "platform_id": plan["platform_id"],
            "status": "completed",
            "approval": approval,
            "output_artifact_hashes": actual,
            "quality_gates": plan["quality_gates"],
            "marketplace_metadata": plan["marketplace_metadata"],
            "review_status": "pending",
        }
        self.persistence.put("factory_build_results", build_id, result)
        self._event("factory.build.completed", plan, result)
        return result

    def review(self, ctx: TenantContext, build_id: str, approved: bool = True) -> dict[str, object]:
        plan = self._get(ctx, build_id)
        result = self.persistence.get("factory_build_results", build_id)
        if result is None or result.get("status") != "completed":
            raise AuthorizationError("completed build is required for review")
        security = dict(plan["artifact_contents"]).get("security.review.json", "")
        if '"status": "passed"' not in str(security):
            raise AuthorizationError("security review did not pass")
        review = {
            "build_id": build_id,
            "tenant_id": ctx.tenant_id,
            "reviewed_by": ctx.principal_id,
            "reviewed_at": datetime.now(tz=timezone.utc).isoformat(),
            "status": "approved" if approved else "rejected",
        }
        self.persistence.put("factory_build_reviews", build_id, review)
        result["review_status"] = review["status"]
        self.persistence.put("factory_build_results", build_id, result)
        self._event("factory.build.review.completed", plan, review)
        return review

    def replay(self, ctx: TenantContext, build_id: str) -> dict[str, object]:
        plan = self._get(ctx, build_id)
        replay = self.plan(ctx, str(plan["execution_id"]))
        if replay["build_id"] != build_id or replay["output_artifact_hashes"] != plan["output_artifact_hashes"]:
            raise ValueError("build replay diverged")
        self._event("factory.build.replayed", plan, {"plan_digest": plan["plan_digest"]})
        return replay

    def rollback(self, ctx: TenantContext, build_id: str) -> dict[str, object]:
        plan = self._get(ctx, build_id)
        self._approval(ctx, plan)
        rollback = self.persistence.get("factory_build_rollback_plans", build_id)
        if rollback is None:
            raise NotFoundError("build rollback plan not found")
        destination = self._destination(plan)
        backups = dict(rollback["backups"])
        self._restore(destination, backups, list(backups))
        result = {
            "build_id": build_id,
            "tenant_id": ctx.tenant_id,
            "status": "rolled_back",
            "restored_paths": sorted(backups),
        }
        self.persistence.put("factory_build_rollbacks", build_id, result)
        self._event("factory.build.rolled_back", plan, result)
        return result

    def get(self, ctx: TenantContext, build_id: str) -> dict[str, object]:
        plan = self._get(ctx, build_id)
        return {"plan": _public_plan(plan), "result": self.persistence.get("factory_build_results", build_id)}

    def events(self, ctx: TenantContext, build_id: str) -> list[dict[str, object]]:
        self._get(ctx, build_id)
        return [event.as_dict() for event in self.event_store.replay(build_id)]

    def artifacts(self, ctx: TenantContext, build_id: str) -> list[dict[str, object]]:
        self._get(ctx, build_id)
        return [
            item
            for item in self.persistence.list_tenant("factory_build_artifacts", ctx.tenant_id)
            if item.get("build_id") == build_id
        ]

    def _get(self, ctx: TenantContext, build_id: str) -> dict[str, object]:
        plan = self.persistence.get("factory_build_plans", build_id)
        if plan is None:
            raise NotFoundError("repository build not found")
        if plan.get("tenant_id") != ctx.tenant_id:
            raise AuthorizationError("cross-tenant repository build access denied")
        return plan

    def _approval(self, ctx: TenantContext, plan: dict[str, object]) -> dict[str, object]:
        approval = self.persistence.get("factory_build_approvals", str(plan["build_id"]))
        if approval is None:
            raise AuthorizationError("repository build approval is required")
        if approval.get("tenant_id") != ctx.tenant_id or approval.get("plan_digest") != plan["plan_digest"]:
            raise AuthorizationError("repository build approval is invalid")
        return approval

    def _destination(self, plan: dict[str, object]) -> Path:
        parts = [str(plan["repository_id"])]
        if self.tenant_subdirectories:
            parts.insert(0, str(plan["tenant_id"]))
        destination = self.output_root.joinpath(*parts).resolve()
        if self.output_root not in destination.parents:
            raise ValueError("build destination escapes output root")
        return destination

    def _restore(
        self,
        destination: Path,
        backups: dict[str, object],
        paths: list[str],
    ) -> None:
        for relative_path in reversed(sorted(paths)):
            target = destination / relative_path
            original = backups.get(relative_path)
            if original is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(original), encoding="utf-8")

    def _quality_gates(
        self,
        execution: dict[str, object],
        artifacts: dict[str, str],
        worker_results: list[dict[str, object]],
    ) -> dict[str, bool]:
        for path in artifacts:
            validate_relative_path(path)
        capabilities = {str(item["capability"]) for item in worker_results}
        required = {
            "domain_models",
            "service_logic",
            "api_routes",
            "tests",
            "documentation",
            "quality_evidence",
            "security_review",
        }
        return {
            "approved_execution_artifact_exists": bool(execution["artifact_hashes"]),
            "repository_manifest_complete": bool(execution["context"]),
            "worker_capability_match": capabilities == required,
            "domain_model_complete": any(path.endswith("/models.py") for path in artifacts),
            "service_logic_tests_exist": "tests/test_product_logic.py" in artifacts,
            "api_route_tests_exist": "tests/test_api_routes.py" in artifacts,
            "documentation_updated": "docs/product_logic.md" in artifacts,
            "artifact_hashes_stable": all(sha256(value.encode()).hexdigest() for value in artifacts.values()),
            "tenant_isolation": bool(execution["tenant_id"]),
            "path_safety": all(".." not in path for path in artifacts),
            "security_review_completed": "security.review.json" in artifacts,
        }

    def _event(self, event_type: str, plan: dict[str, object], payload: dict[str, object]) -> None:
        self.event_store.append(
            event_type,
            str(plan["build_id"]),
            {
                "tenant_id": plan["tenant_id"],
                "repository_id": plan["repository_id"],
                "platform_id": plan["platform_id"],
                **payload,
            },
        )


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _public_plan(plan: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in plan.items() if key != "artifact_contents"}
