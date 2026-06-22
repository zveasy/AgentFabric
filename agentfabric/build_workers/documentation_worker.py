"""Product documentation build worker."""

from .product_logic import product_artifacts
from .worker_context import WorkerContext
from .worker_manifest import WorkerManifest
from .worker_result import WorkerResult


class DocumentationWorker:
    manifest = WorkerManifest(
        "documentation-worker",
        "documentation",
        ("service", "ai_agent", "frontend"),
        ("construction",),
        quality_gates=("documentation_updated",),
    )

    def run(self, context: WorkerContext) -> WorkerResult:
        artifacts = product_artifacts(context.repository_id)
        path = "docs/product_logic.md"
        return WorkerResult(self.manifest.worker_id, self.manifest.capability, {path: artifacts[path]}, {"updated": True})
