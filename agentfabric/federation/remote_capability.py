"""Remote capability metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RemoteCapability:
    name: str
    version: str = "1.0.0"
    data_classes: tuple[str, ...] = ("public",)
    workflow_types: tuple[str, ...] = ()
    package_signature_verified: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "data_classes": list(self.data_classes),
            "workflow_types": list(self.workflow_types),
            "package_signature_verified": self.package_signature_verified,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "RemoteCapability":
        return cls(
            name=str(value["name"]),
            version=str(value.get("version", "1.0.0")),
            data_classes=tuple(str(item) for item in value.get("data_classes", ("public",))),
            workflow_types=tuple(str(item) for item in value.get("workflow_types", ())),
            package_signature_verified=bool(value.get("package_signature_verified", True)),
        )
