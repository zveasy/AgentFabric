"""Enterprise connector manifests."""

from __future__ import annotations

from dataclasses import dataclass, field


SUPPORTED_CONNECTOR_TYPES = {
    "gmail",
    "google_workspace",
    "microsoft_365",
    "slack",
    "teams",
    "jira",
    "servicenow",
    "confluence",
    "sharepoint",
    "s3",
    "github",
}


@dataclass(frozen=True)
class ConnectorManifest:
    connector_type: str
    display_name: str
    capabilities: tuple[str, ...] = ("sync", "search", "fetch")
    scopes: tuple[str, ...] = ()
    data_classes: tuple[str, ...] = ()
    webhook_supported: bool = False
    metadata: dict[str, object] = field(default_factory=dict)

    def validate(self) -> None:
        if self.connector_type not in SUPPORTED_CONNECTOR_TYPES:
            raise ValueError(f"unsupported connector type: {self.connector_type}")
        if not self.display_name:
            raise ValueError("connector display_name is required")

    def as_dict(self) -> dict[str, object]:
        return {
            "connector_type": self.connector_type,
            "display_name": self.display_name,
            "capabilities": list(self.capabilities),
            "scopes": list(self.scopes),
            "data_classes": list(self.data_classes),
            "webhook_supported": self.webhook_supported,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "ConnectorManifest":
        return cls(
            connector_type=str(value["connector_type"]),
            display_name=str(value.get("display_name", value["connector_type"])),
            capabilities=tuple(str(item) for item in value.get("capabilities", ("sync", "search", "fetch"))),
            scopes=tuple(str(item) for item in value.get("scopes", ())),
            data_classes=tuple(str(item) for item in value.get("data_classes", ())),
            webhook_supported=bool(value.get("webhook_supported", False)),
            metadata=dict(value.get("metadata", {})),
        )
