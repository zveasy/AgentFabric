"""Billing and idempotent metering pipeline primitives."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass

from agentfabric.phase2.models import MeterEvent


@dataclass(frozen=True)
class InvoiceLine:
    event_type: str
    quantity: int
    unit_price: float

    @property
    def subtotal(self) -> float:
        return round(self.quantity * self.unit_price, 4)


class BillingService:
    """Queue-based metering with idempotent processing."""

    DEFAULT_PRICING = {
        "install": 0.05,
        "run": 0.01,
        "subscription_month": 29.0,
    }

    def __init__(self) -> None:
        self._queue: deque[MeterEvent] = deque()
        self._processed_idempotency_keys: set[str] = set()
        self._usage_by_tenant: defaultdict[str, Counter[str]] = defaultdict(Counter)
        self._pricing = dict(self.DEFAULT_PRICING)

    def set_price(self, event_type: str, unit_price: float) -> None:
        self._pricing[event_type] = unit_price

    def enqueue(self, event: MeterEvent) -> None:
        self._queue.append(event)

    def process_queue(self) -> None:
        while self._queue:
            event = self._queue.popleft()
            if event.idempotency_key in self._processed_idempotency_keys:
                continue
            self._processed_idempotency_keys.add(event.idempotency_key)
            self._usage_by_tenant[event.tenant_id][event.event_type] += 1

    def build_invoice(self, tenant_id: str) -> dict[str, object]:
        usage = self._usage_by_tenant[tenant_id]
        lines: list[InvoiceLine] = []
        for event_type, qty in sorted(usage.items()):
            unit_price = self._pricing.get(event_type, 0.0)
            lines.append(InvoiceLine(event_type=event_type, quantity=qty, unit_price=unit_price))
        total = round(sum(line.subtotal for line in lines), 4)
        return {
            "tenant_id": tenant_id,
            "lines": [line.__dict__ | {"subtotal": line.subtotal} for line in lines],
            "total": total,
        }
