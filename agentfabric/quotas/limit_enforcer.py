"""Hard quota enforcement."""

from __future__ import annotations

from agentfabric.errors import ConflictError

from .quota_policy import QuotaPolicy
from .quota_tracker import QuotaTracker


class LimitEnforcer:
    def __init__(self, tracker: QuotaTracker) -> None:
        self.tracker = tracker

    def check(self, tenant_id: str, policy: QuotaPolicy, counter: str, amount: int = 1) -> None:
        limit = getattr(policy, counter)
        current = self.tracker.usage(tenant_id).get(counter)
        if current + amount > limit:
            raise ConflictError(f"quota exceeded: {counter}")

    def consume(self, tenant_id: str, policy: QuotaPolicy, counter: str, amount: int = 1) -> int:
        self.check(tenant_id, policy, counter, amount)
        return self.tracker.increment(tenant_id, counter, amount)
