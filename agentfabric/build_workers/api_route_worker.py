"""API route build worker."""

from .product_logic import product_artifacts
from .worker_context import WorkerContext
from .worker_manifest import WorkerManifest
from .worker_result import WorkerResult


class ApiRouteWorker:
    manifest = WorkerManifest(
        "api-route-worker",
        "api_routes",
        ("service", "ai_agent", "frontend"),
        ("construction",),
        quality_gates=("api_route_tests",),
    )

    def run(self, context: WorkerContext) -> WorkerResult:
        path = f"src/{context.repository_id}/api.py"
        return WorkerResult(self.manifest.worker_id, self.manifest.capability, {path: product_artifacts(context.repository_id)[path]}, {"routes_declared": True})
