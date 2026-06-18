"""Cloud runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    queue_backend: str = "memory"
    sqlite_path: str = "agentfabric_runtime_queue.db"
    redis_url: str = "redis://localhost:6379/0"
    max_attempts: int = 3
    worker_lease_seconds: int = 60
    heartbeat_timeout_seconds: int = 90
    production_fail_closed: bool = False
