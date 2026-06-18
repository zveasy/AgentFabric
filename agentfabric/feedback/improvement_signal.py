"""Derived improvement signals."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImprovementSignal:
    tenant_id: str
    target_type: str
    target_id: str
    signal_type: str
    severity: str
    summary: str

    def as_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "signal_type": self.signal_type,
            "severity": self.severity,
            "summary": self.summary,
        }
