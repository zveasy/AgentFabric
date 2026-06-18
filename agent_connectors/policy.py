"""Fail-closed connector execution policies."""

from __future__ import annotations

from dataclasses import dataclass


RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass(frozen=True)
class ConnectorExecutionPolicy:
    policy_id: str
    tenant_id: str
    allowed_agents: tuple[str, ...] = ()
    allowed_connectors: tuple[str, ...] = ()
    allowed_actions: tuple[str, ...] = ()
    allowed_credential_types: tuple[str, ...] = ()
    maximum_risk: str = "medium"
    minimum_package_trust_score: float = 0.8
    require_veil: bool = True

    def validate(self) -> None:
        if not self.policy_id or not self.tenant_id:
            raise ValueError("policy_id and tenant_id are required")
        if self.maximum_risk not in RISK_ORDER:
            raise ValueError("invalid maximum_risk")
        if not 0 <= self.minimum_package_trust_score <= 1:
            raise ValueError("minimum package trust score must be between 0 and 1")

    def as_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "tenant_id": self.tenant_id,
            "allowed_agents": list(self.allowed_agents),
            "allowed_connectors": list(self.allowed_connectors),
            "allowed_actions": list(self.allowed_actions),
            "allowed_credential_types": list(self.allowed_credential_types),
            "maximum_risk": self.maximum_risk,
            "minimum_package_trust_score": self.minimum_package_trust_score,
            "require_veil": self.require_veil,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "ConnectorExecutionPolicy":
        return cls(
            policy_id=str(value["policy_id"]),
            tenant_id=str(value["tenant_id"]),
            allowed_agents=tuple(str(item) for item in value.get("allowed_agents", ())),
            allowed_connectors=tuple(str(item) for item in value.get("allowed_connectors", ())),
            allowed_actions=tuple(str(item) for item in value.get("allowed_actions", ())),
            allowed_credential_types=tuple(str(item) for item in value.get("allowed_credential_types", ())),
            maximum_risk=str(value.get("maximum_risk", "medium")),
            minimum_package_trust_score=float(value.get("minimum_package_trust_score", 0.8)),
            require_veil=bool(value.get("require_veil", True)),
        )

    def decide(
        self,
        *,
        agent_id: str,
        connector_id: str,
        action: str,
        credential_type: str,
        risk_level: str,
        package_trust_score: float,
    ) -> "PolicyDecision":
        reasons = []
        if self.allowed_agents and agent_id not in self.allowed_agents:
            reasons.append("agent is not allowlisted")
        if self.allowed_connectors and connector_id not in self.allowed_connectors:
            reasons.append("connector is not allowlisted")
        if self.allowed_actions and action not in self.allowed_actions:
            reasons.append("action is not allowlisted")
        if self.allowed_credential_types and credential_type not in self.allowed_credential_types:
            reasons.append("credential type is not allowed")
        if RISK_ORDER[risk_level] > RISK_ORDER[self.maximum_risk]:
            reasons.append("connector risk exceeds policy threshold")
        if package_trust_score < self.minimum_package_trust_score:
            reasons.append("marketplace package trust score is too low")
        return PolicyDecision(not reasons, tuple(reasons), self.policy_id)


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reasons: tuple[str, ...]
    policy_id: str

    def as_dict(self) -> dict[str, object]:
        return {"allowed": self.allowed, "reasons": list(self.reasons), "policy_id": self.policy_id}
