"""Capability declarations for mesh-aware agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AgentCapability(str, Enum):
    RESEARCH = "research"
    CODING = "coding"
    ANALYSIS = "analysis"
    REVIEW = "review"
    RETRIEVAL = "retrieval"
    PLANNING = "planning"
    EXECUTION = "execution"


@dataclass(frozen=True)
class CapabilityManifest:
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        normalized = tuple(sorted({str(item).lower() for item in self.capabilities}))
        invalid = [item for item in normalized if item not in {cap.value for cap in AgentCapability}]
        if invalid:
            raise ValueError(f"unsupported capabilities: {', '.join(invalid)}")
        object.__setattr__(self, "capabilities", normalized)

    def supports(self, capability: str) -> bool:
        return capability.lower() in self.capabilities

    def as_dict(self) -> dict[str, object]:
        return {"capabilities": list(self.capabilities)}
