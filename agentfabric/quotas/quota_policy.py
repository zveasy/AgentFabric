"""Quota policy definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuotaPolicy:
    agents_per_tenant: int = 10
    workflow_runs_per_day: int = 100
    concurrent_workflows: int = 5
    mesh_messages_per_minute: int = 1000
    memory_records: int = 1000
    event_retention: int = 100000
    marketplace_installs: int = 100
    api_calls: int = 10000
    storage_bytes: int = 10_000_000
    compute_seconds: int = 3600

    def as_dict(self) -> dict[str, int]:
        return {
            "agents_per_tenant": self.agents_per_tenant,
            "workflow_runs_per_day": self.workflow_runs_per_day,
            "concurrent_workflows": self.concurrent_workflows,
            "mesh_messages_per_minute": self.mesh_messages_per_minute,
            "memory_records": self.memory_records,
            "event_retention": self.event_retention,
            "marketplace_installs": self.marketplace_installs,
            "api_calls": self.api_calls,
            "storage_bytes": self.storage_bytes,
            "compute_seconds": self.compute_seconds,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "QuotaPolicy":
        defaults = cls().as_dict()
        defaults.update({key: int(item) for key, item in value.items() if key in defaults})
        return cls(**defaults)
