"""Governance policy constraints."""

from __future__ import annotations

from dataclasses import dataclass


RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass(frozen=True)
class GovernancePolicy:
    policy_id: str
    tenant_id: str
    organization_id: str
    max_agent_authority_risk: str = "medium"
    human_required_risks: tuple[str, ...] = ("high", "critical")
    security_required_actions: tuple[str, ...] = ("tool_permission_escalation", "external_api_call")
    compliance_required_actions: tuple[str, ...] = ("tenant_configuration_change", "marketplace_publish")
    high_risk_self_approval_allowed: bool = False

    def requires_human(self, risk_level: str) -> bool:
        return risk_level in self.human_required_risks

    def risk_within_agent_authority(self, risk_level: str) -> bool:
        return RISK_ORDER.get(risk_level, 99) <= RISK_ORDER.get(self.max_agent_authority_risk, 0)

    def as_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "max_agent_authority_risk": self.max_agent_authority_risk,
            "human_required_risks": list(self.human_required_risks),
            "security_required_actions": list(self.security_required_actions),
            "compliance_required_actions": list(self.compliance_required_actions),
            "high_risk_self_approval_allowed": self.high_risk_self_approval_allowed,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "GovernancePolicy":
        return cls(
            policy_id=str(value["policy_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            max_agent_authority_risk=str(value.get("max_agent_authority_risk", "medium")),
            human_required_risks=tuple(str(item) for item in value.get("human_required_risks", ("high", "critical"))),
            security_required_actions=tuple(str(item) for item in value.get("security_required_actions", ())),
            compliance_required_actions=tuple(str(item) for item in value.get("compliance_required_actions", ())),
            high_risk_self_approval_allowed=bool(value.get("high_risk_self_approval_allowed", False)),
        )
