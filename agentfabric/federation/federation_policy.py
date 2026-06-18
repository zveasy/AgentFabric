"""Federation policy constraints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FederationPolicy:
    tenant_id: str
    organization_id: str
    allowed_capabilities: tuple[str, ...] = ()
    denied_capabilities: tuple[str, ...] = ()
    permitted_data_classes: tuple[str, ...] = ("public", "internal")
    allowed_workflow_types: tuple[str, ...] = ()
    min_reputation_score: float = 0.0
    blocked_remote_orgs: tuple[str, ...] = ()
    blocked_remote_agents: tuple[str, ...] = ()
    blocked_publishers: tuple[str, ...] = ()
    compromised_keys: tuple[str, ...] = ()

    def allows_capability(self, capability: str) -> bool:
        if capability in self.denied_capabilities:
            return False
        return not self.allowed_capabilities or capability in self.allowed_capabilities

    def as_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "allowed_capabilities": list(self.allowed_capabilities),
            "denied_capabilities": list(self.denied_capabilities),
            "permitted_data_classes": list(self.permitted_data_classes),
            "allowed_workflow_types": list(self.allowed_workflow_types),
            "min_reputation_score": self.min_reputation_score,
            "blocked_remote_orgs": list(self.blocked_remote_orgs),
            "blocked_remote_agents": list(self.blocked_remote_agents),
            "blocked_publishers": list(self.blocked_publishers),
            "compromised_keys": list(self.compromised_keys),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "FederationPolicy":
        return cls(
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            allowed_capabilities=tuple(str(item) for item in value.get("allowed_capabilities", ())),
            denied_capabilities=tuple(str(item) for item in value.get("denied_capabilities", ())),
            permitted_data_classes=tuple(str(item) for item in value.get("permitted_data_classes", ("public", "internal"))),
            allowed_workflow_types=tuple(str(item) for item in value.get("allowed_workflow_types", ())),
            min_reputation_score=float(value.get("min_reputation_score", 0.0)),
            blocked_remote_orgs=tuple(str(item) for item in value.get("blocked_remote_orgs", ())),
            blocked_remote_agents=tuple(str(item) for item in value.get("blocked_remote_agents", ())),
            blocked_publishers=tuple(str(item) for item in value.get("blocked_publishers", ())),
            compromised_keys=tuple(str(item) for item in value.get("compromised_keys", ())),
        )
