"""Connector access policy."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectorPolicy:
    allowed_operations: tuple[str, ...] = ("sync", "search", "fetch", "webhook", "health")
    allowed_data_classes: tuple[str, ...] = ()
    max_results: int = 100
    require_veil: bool = True

    def allows(self, operation: str, data_class: str | None = None) -> bool:
        if operation not in self.allowed_operations:
            return False
        if data_class and self.allowed_data_classes and data_class not in self.allowed_data_classes:
            return False
        return True

    def as_dict(self) -> dict[str, object]:
        return {
            "allowed_operations": list(self.allowed_operations),
            "allowed_data_classes": list(self.allowed_data_classes),
            "max_results": self.max_results,
            "require_veil": self.require_veil,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "ConnectorPolicy":
        return cls(
            allowed_operations=tuple(str(item) for item in value.get("allowed_operations", ("sync", "search", "fetch", "webhook", "health"))),
            allowed_data_classes=tuple(str(item) for item in value.get("allowed_data_classes", ())),
            max_results=int(value.get("max_results", 100)),
            require_veil=bool(value.get("require_veil", True)),
        )
