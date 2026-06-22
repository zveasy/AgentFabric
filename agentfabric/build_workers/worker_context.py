"""Approved input context for a build worker."""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerContext:
    tenant_id: str
    platform_id: str
    repository_id: str
    repository_type: str
    domain: str
    execution_id: str
    input_artifact_hashes: dict[str, str]
