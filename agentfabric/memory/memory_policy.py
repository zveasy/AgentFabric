"""Retention and deletion policy for durable memory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .memory_record import MemoryRecord


@dataclass(frozen=True)
class MemoryPolicy:
    short_term_ttl_days: int = 7
    long_term_ttl_days: int | None = None
    allow_delete: bool = True

    def expired(self, record: MemoryRecord, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(tz=timezone.utc)
        ttl_days = self.short_term_ttl_days if record.memory_type == "short_term" else self.long_term_ttl_days
        if ttl_days is None:
            return False
        return record.created_at + timedelta(days=ttl_days) <= current

    def can_delete(self, record: MemoryRecord) -> bool:
        return self.allow_delete and record.classification != "legal_hold"
