"""Indexes for scoped memory lookups."""

from __future__ import annotations

from collections import defaultdict

from .memory_record import MemoryRecord


class MemoryIndex:
    def __init__(self) -> None:
        self.by_agent: defaultdict[str, set[str]] = defaultdict(set)
        self.by_tenant_agent: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
        self.by_workflow: defaultdict[str, set[str]] = defaultdict(set)

    def add(self, record: MemoryRecord) -> None:
        self.by_agent[record.owner_agent_id].add(record.memory_id)
        self.by_tenant_agent[(record.tenant_id, record.owner_agent_id)].add(record.memory_id)
        if record.source_workflow_id:
            self.by_workflow[record.source_workflow_id].add(record.memory_id)

    def remove(self, record: MemoryRecord) -> None:
        self.by_agent[record.owner_agent_id].discard(record.memory_id)
        self.by_tenant_agent[(record.tenant_id, record.owner_agent_id)].discard(record.memory_id)
        if record.source_workflow_id:
            self.by_workflow[record.source_workflow_id].discard(record.memory_id)
