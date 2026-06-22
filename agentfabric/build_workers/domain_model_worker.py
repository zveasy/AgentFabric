"""Domain model build worker."""

from .product_logic import product_artifacts
from .worker_context import WorkerContext
from .worker_manifest import WorkerManifest
from .worker_result import WorkerResult


class DomainModelWorker:
    manifest = WorkerManifest(
        "domain-model-worker",
        "domain_models",
        ("service", "ai_agent", "frontend"),
        ("construction",),
        quality_gates=("domain_model_completeness",),
    )

    def run(self, context: WorkerContext) -> WorkerResult:
        path = f"src/{context.repository_id}/models.py"
        return WorkerResult(self.manifest.worker_id, self.manifest.capability, {path: product_artifacts(context.repository_id)[path]}, {"complete": True})
