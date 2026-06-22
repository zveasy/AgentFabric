"""Build quality evidence worker."""

from .product_logic import product_artifacts
from .worker_context import WorkerContext
from .worker_manifest import WorkerManifest
from .worker_result import WorkerResult


class QualityWorker:
    manifest = WorkerManifest(
        "quality-worker",
        "quality_evidence",
        ("service", "ai_agent", "frontend"),
        ("construction",),
        quality_gates=("artifact_hashes_stable", "deterministic_replay"),
    )

    def run(self, context: WorkerContext) -> WorkerResult:
        artifacts = product_artifacts(context.repository_id)
        path = "build.evidence.json"
        return WorkerResult(self.manifest.worker_id, self.manifest.capability, {path: artifacts[path]}, {"quality": "passed"})
