"""Fail-closed build worker registry."""

from __future__ import annotations

from typing import Protocol

from .worker_context import WorkerContext
from .worker_manifest import WorkerManifest
from .worker_result import WorkerResult


class BuildWorker(Protocol):
    manifest: WorkerManifest

    def run(self, context: WorkerContext) -> WorkerResult:
        """Produce deterministic artifacts."""


class WorkerRegistry:
    def __init__(self) -> None:
        self._workers: dict[str, BuildWorker] = {}

    def register(self, worker: BuildWorker) -> None:
        worker.manifest.validate()
        if worker.manifest.worker_id in self._workers:
            raise ValueError("build worker is already registered")
        self._workers[worker.manifest.worker_id] = worker

    def get(self, worker_id: str, context: WorkerContext) -> BuildWorker:
        try:
            worker = self._workers[worker_id]
        except KeyError as exc:
            raise ValueError("build worker is not registered") from exc
        manifest = worker.manifest
        if context.repository_type not in manifest.allowed_repository_types:
            raise ValueError("build worker does not support repository type")
        if context.domain not in manifest.allowed_domains:
            raise ValueError("build worker does not support repository domain")
        if not context.input_artifact_hashes:
            raise ValueError("build worker input artifacts are required")
        return worker

    def list(self) -> list[dict[str, object]]:
        return [self._workers[key].manifest.as_dict() for key in sorted(self._workers)]
