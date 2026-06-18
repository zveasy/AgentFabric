"""Tool permission contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolPermission:
    required_rbac_scope: str
    required_tenant_context: bool = True
    required_connector_policy: bool = True
    required_veil_policy_check: bool = True
    governance_approval_required: bool = False
    result_persistence_allowed: bool = True
    allowed_output_classifications: tuple[str, ...] = ("public", "internal")

    def as_dict(self) -> dict[str, object]:
        return {
            "required_rbac_scope": self.required_rbac_scope,
            "required_tenant_context": self.required_tenant_context,
            "required_connector_policy": self.required_connector_policy,
            "required_veil_policy_check": self.required_veil_policy_check,
            "governance_approval_required": self.governance_approval_required,
            "result_persistence_allowed": self.result_persistence_allowed,
            "allowed_output_classifications": list(self.allowed_output_classifications),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "ToolPermission":
        return cls(
            required_rbac_scope=str(value.get("required_rbac_scope", "tools.execute")),
            required_tenant_context=bool(value.get("required_tenant_context", True)),
            required_connector_policy=bool(value.get("required_connector_policy", True)),
            required_veil_policy_check=bool(value.get("required_veil_policy_check", True)),
            governance_approval_required=bool(value.get("governance_approval_required", False)),
            result_persistence_allowed=bool(value.get("result_persistence_allowed", True)),
            allowed_output_classifications=tuple(str(item) for item in value.get("allowed_output_classifications", ("public", "internal"))),
        )
