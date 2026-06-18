"""Durable tenant-scoped memory store."""

from __future__ import annotations

from copy import deepcopy

from agentfabric.persistence import PersistenceStore

from .memory_index import MemoryIndex
from .memory_policy import MemoryPolicy
from .memory_record import MemoryRecord


class DurableMemoryStore:
    def __init__(self, persistence: PersistenceStore, policy: MemoryPolicy | None = None) -> None:
        self.persistence = persistence
        self.policy = policy or MemoryPolicy()
        self.index = MemoryIndex()
        self.records: dict[str, MemoryRecord] = {}
        self.persistence.initialize()
        for item in self.persistence.list("runtime_memory"):
            record = MemoryRecord.from_dict(item)
            self.records[record.memory_id] = record
            self.index.add(record)

    def put(self, record: MemoryRecord) -> MemoryRecord:
        _reject_raw_sensitive(record.content)
        self.records[record.memory_id] = record
        self.index.add(record)
        self.persistence.put("runtime_memory", record.memory_id, record.as_dict())
        return record

    def create(
        self,
        *,
        owner_agent_id: str,
        tenant_id: str,
        content: dict[str, object],
        classification: str = "internal",
        source_workflow_id: str | None = None,
        veil_token_refs: tuple[str, ...] = (),
        memory_type: str = "short_term",
    ) -> MemoryRecord:
        return self.put(
            MemoryRecord(
                owner_agent_id=owner_agent_id,
                tenant_id=tenant_id,
                source_workflow_id=source_workflow_id,
                classification=classification,
                content=deepcopy(content),
                veil_token_refs=veil_token_refs,
                memory_type=memory_type,
            )
        )

    def list_for_agent(self, *, tenant_id: str, owner_agent_id: str) -> list[MemoryRecord]:
        memory_ids = self.index.by_tenant_agent[(tenant_id, owner_agent_id)]
        records = [self.records[memory_id] for memory_id in sorted(memory_ids)]
        for record in records:
            record.touch()
            self.persistence.put("runtime_memory", record.memory_id, record.as_dict())
        return records

    def delete(self, *, tenant_id: str, owner_agent_id: str, memory_id: str) -> bool:
        record = self.records.get(memory_id)
        if record is None or record.tenant_id != tenant_id or record.owner_agent_id != owner_agent_id:
            return False
        if not self.policy.can_delete(record):
            raise PermissionError("memory deletion denied by policy")
        self.index.remove(record)
        del self.records[memory_id]
        return self.persistence.delete("runtime_memory", memory_id)

    def enforce_retention(self) -> int:
        removed = 0
        for record in list(self.records.values()):
            if self.policy.expired(record) and self.policy.can_delete(record):
                if self.delete(
                    tenant_id=record.tenant_id,
                    owner_agent_id=record.owner_agent_id,
                    memory_id=record.memory_id,
                ):
                    removed += 1
        return removed


def _reject_raw_sensitive(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"raw", "secret", "password", "token"} or lowered.startswith("raw_"):
                raise ValueError("raw sensitive values must remain behind VEIL/Aegis references")
            _reject_raw_sensitive(item)
    elif isinstance(value, list):
        for item in value:
            _reject_raw_sensitive(item)
