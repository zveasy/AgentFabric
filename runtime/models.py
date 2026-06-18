from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TrustProfile:
    level: str
    policy_requirements: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionPolicy:
    require_audit: bool = True
    fail_closed: bool = True
    max_tool_calls: int = 0


@dataclass(frozen=True)
class MemoryPolicy:
    allow_long_term_memory: bool = False
    tenant_scoped: bool = True
    require_sanitization: bool = True


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    name: str
    purpose: str
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    trust_profile: TrustProfile = field(default_factory=lambda: TrustProfile(level="restricted"))
    input_schema: dict[str, object] = field(default_factory=dict)
    output_schema: dict[str, object] = field(default_factory=dict)
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    memory_policy: MemoryPolicy = field(default_factory=MemoryPolicy)
