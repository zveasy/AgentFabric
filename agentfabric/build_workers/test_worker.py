"""Product and API test build worker."""

from .product_logic import product_artifacts
from .worker_context import WorkerContext
from .worker_manifest import WorkerManifest
from .worker_result import WorkerResult


class TestWorker:
    manifest = WorkerManifest(
        "test-worker",
        "tests",
        ("service", "ai_agent", "frontend"),
        ("construction",),
        quality_gates=("service_logic_tests", "api_route_tests"),
    )

    def run(self, context: WorkerContext) -> WorkerResult:
        all_artifacts = product_artifacts(context.repository_id)
        artifacts = {key: value for key, value in all_artifacts.items() if key.startswith("tests/")}
        return WorkerResult(self.manifest.worker_id, self.manifest.capability, artifacts, {"test_files": len(artifacts)})
