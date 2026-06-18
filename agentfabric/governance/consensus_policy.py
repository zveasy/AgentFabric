"""Consensus policy configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConsensusPolicy:
    mode: str = "majority"
    threshold: float = 0.5
    required_roles: tuple[str, ...] = ()
    required_approvals: int = 1

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "threshold": self.threshold,
            "required_roles": list(self.required_roles),
            "required_approvals": self.required_approvals,
        }
