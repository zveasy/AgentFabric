"""Tool manifests for governed agent tooling."""

from __future__ import annotations

from dataclasses import dataclass, field


SUPPORTED_TOOL_TYPES = {
    "connector_search",
    "connector_fetch",
    "document_summary",
    "ticket_analysis",
    "email_analysis",
    "code_repository_review",
    "audit_bundle_generation",
    "governance_proposal_creation",
    "marketplace_package_verification",
}


@dataclass(frozen=True)
class ToolManifest:
    name: str
    tool_type: str
    description: str = ""
    version: str = "1.0.0"
    required_connector_type: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def validate(self) -> None:
        if self.tool_type not in SUPPORTED_TOOL_TYPES:
            raise ValueError(f"unsupported tool type: {self.tool_type}")
        if not self.name:
            raise ValueError("tool name is required")

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "tool_type": self.tool_type,
            "description": self.description,
            "version": self.version,
            "required_connector_type": self.required_connector_type,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "ToolManifest":
        return cls(
            name=str(value["name"]),
            tool_type=str(value["tool_type"]),
            description=str(value.get("description", "")),
            version=str(value.get("version", "1.0.0")),
            required_connector_type=str(value["required_connector_type"]) if value.get("required_connector_type") else None,
            metadata=dict(value.get("metadata", {})),
        )
