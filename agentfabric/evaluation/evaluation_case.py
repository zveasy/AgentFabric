"""Evaluation case definitions."""

from __future__ import annotations

from dataclasses import dataclass, field


SENSITIVE_KEYS = {"raw", "secret", "password", "token_value", "private_key", "credential"}


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    input_ref: str
    expected_output: dict[str, object] = field(default_factory=dict)
    target_type: str = "agent_output"
    target_id: str = ""
    metric_weights: dict[str, float] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.case_id or not self.input_ref:
            raise ValueError("evaluation case requires case_id and input_ref")
        if _contains_sensitive_key(self.expected_output):
            raise ValueError("raw sensitive values are not allowed in evaluation cases")

    def as_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "input_ref": self.input_ref,
            "expected_output": dict(self.expected_output),
            "target_type": self.target_type,
            "target_id": self.target_id,
            "metric_weights": dict(self.metric_weights),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "EvaluationCase":
        return cls(
            case_id=str(value["case_id"]),
            input_ref=str(value["input_ref"]),
            expected_output=dict(value.get("expected_output", {})),
            target_type=str(value.get("target_type", "agent_output")),
            target_id=str(value.get("target_id", "")),
            metric_weights={str(key): float(item) for key, item in dict(value.get("metric_weights", {})).items()},
        )


def _contains_sensitive_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                return True
            if _contains_sensitive_key(item):
                return True
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False
