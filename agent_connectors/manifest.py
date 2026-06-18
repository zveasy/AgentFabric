"""Versioned enterprise connector manifests."""

from __future__ import annotations

from dataclasses import dataclass, field


SUPPORTED_CONNECTOR_TYPES = {
    "gmail",
    "google_calendar",
    "slack",
    "teams",
    "jira",
    "github",
    "salesforce",
    "servicenow",
    "sharepoint",
    "s3",
    "custom_http",
}

RISK_LEVELS = {"low", "medium", "high", "critical"}


@dataclass(frozen=True)
class ConnectorManifest:
    connector_id: str
    name: str
    version: str
    description: str
    connector_type: str
    supported_actions: tuple[str, ...]
    required_permissions: tuple[str, ...]
    credential_type: str
    rate_limits: dict[str, int] = field(default_factory=lambda: {"requests_per_minute": 60})
    risk_level: str = "medium"
    tenant_scope: str = "tenant"
    allowed_domains: tuple[str, ...] = ()
    allowed_http_methods: tuple[str, ...] = ("GET", "POST")
    trust_score: float = 1.0

    def validate(self) -> None:
        if not all((self.connector_id, self.name, self.version, self.description, self.credential_type)):
            raise ValueError("connector manifest is missing required fields")
        if self.connector_type not in SUPPORTED_CONNECTOR_TYPES:
            raise ValueError(f"unsupported connector type: {self.connector_type}")
        if not self.supported_actions:
            raise ValueError("connector must declare supported_actions")
        if self.risk_level not in RISK_LEVELS:
            raise ValueError("invalid connector risk_level")
        if self.tenant_scope != "tenant":
            raise ValueError("connectors must be tenant scoped")
        if int(self.rate_limits.get("requests_per_minute", 0)) <= 0:
            raise ValueError("requests_per_minute must be positive")
        if not 0 <= self.trust_score <= 1:
            raise ValueError("connector trust_score must be between 0 and 1")
        from .permissions import permission_for

        expected = {permission_for(self.connector_type, action) for action in self.supported_actions}
        if not expected.issubset(set(self.required_permissions)):
            raise ValueError("connector permissions do not cover supported actions")

    def as_dict(self) -> dict[str, object]:
        return {
            "connector_id": self.connector_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "connector_type": self.connector_type,
            "supported_actions": list(self.supported_actions),
            "required_permissions": list(self.required_permissions),
            "credential_type": self.credential_type,
            "rate_limits": dict(self.rate_limits),
            "risk_level": self.risk_level,
            "tenant_scope": self.tenant_scope,
            "allowed_domains": list(self.allowed_domains),
            "allowed_http_methods": list(self.allowed_http_methods),
            "trust_score": self.trust_score,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "ConnectorManifest":
        return cls(
            connector_id=str(value["connector_id"]),
            name=str(value["name"]),
            version=str(value["version"]),
            description=str(value.get("description", "")),
            connector_type=str(value["connector_type"]),
            supported_actions=tuple(str(item) for item in value.get("supported_actions", ())),
            required_permissions=tuple(str(item) for item in value.get("required_permissions", ())),
            credential_type=str(value.get("credential_type", "api_key")),
            rate_limits={str(key): int(item) for key, item in dict(value.get("rate_limits", {})).items()},
            risk_level=str(value.get("risk_level", "medium")),
            tenant_scope=str(value.get("tenant_scope", "tenant")),
            allowed_domains=tuple(str(item) for item in value.get("allowed_domains", ())),
            allowed_http_methods=tuple(str(item).upper() for item in value.get("allowed_http_methods", ("GET", "POST"))),
            trust_score=float(value.get("trust_score", 1.0)),
        )
