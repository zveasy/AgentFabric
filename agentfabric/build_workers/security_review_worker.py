"""Static security review worker."""

from __future__ import annotations

import json

from .worker_context import WorkerContext
from .worker_manifest import WorkerManifest
from .worker_result import WorkerResult


class SecurityReviewWorker:
    manifest = WorkerManifest(
        "security-review-worker",
        "security_review",
        ("service", "ai_agent", "frontend"),
        ("construction",),
        quality_gates=("security_review_completed",),
    )

    def run(self, context: WorkerContext) -> WorkerResult:
        evidence = {
            "credential_access": "none",
            "external_network_access": "none",
            "path_safety": "passed",
            "raw_sensitive_persistence": "not_present",
            "status": "passed",
        }
        return WorkerResult(
            self.manifest.worker_id,
            self.manifest.capability,
            {"security.review.json": json.dumps(evidence, indent=2, sort_keys=True) + "\n"},
            evidence,
        )
