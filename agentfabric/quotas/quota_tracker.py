"""Tenant quota usage counters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QuotaUsage:
    counters: dict[str, int] = field(default_factory=dict)

    def increment(self, name: str, amount: int = 1) -> int:
        self.counters[name] = self.counters.get(name, 0) + amount
        return self.counters[name]

    def get(self, name: str) -> int:
        return self.counters.get(name, 0)

    def as_dict(self) -> dict[str, int]:
        return dict(self.counters)


class QuotaTracker:
    def __init__(self) -> None:
        self._usage: dict[str, QuotaUsage] = {}

    def usage(self, tenant_id: str) -> QuotaUsage:
        self._usage.setdefault(tenant_id, QuotaUsage())
        return self._usage[tenant_id]

    def increment(self, tenant_id: str, name: str, amount: int = 1) -> int:
        return self.usage(tenant_id).increment(name, amount)
