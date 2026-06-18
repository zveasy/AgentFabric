from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    agent_id: str
    tenant_id: str
    content: str
    sanitized: bool = True
    scope: str = "short_term"
