from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationScorecard:
    agent_id: str
    version: str
    task_success: float
    policy_compliance: float
    hallucination_risk: float
    sensitive_data_leakage: float
    tool_misuse: float
    audit_completeness: float
    reliability: float
