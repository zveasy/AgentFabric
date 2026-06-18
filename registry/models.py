from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentRecord:
    agent_id: str
    version: str
    owner: str
    permissions: tuple[str, ...] = ()
    trust_score: float = 0.0
    evaluation_history: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)
    veil_policy_requirements: tuple[str, ...] = ()
