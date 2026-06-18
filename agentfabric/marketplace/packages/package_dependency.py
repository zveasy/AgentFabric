"""Package dependency declaration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PackageDependency:
    package_id: str
    version_constraint: str
    required: bool = True
    deprecated: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "package_id": self.package_id,
            "version_constraint": self.version_constraint,
            "required": self.required,
            "deprecated": self.deprecated,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "PackageDependency":
        return cls(
            package_id=str(value["package_id"]),
            version_constraint=str(value.get("version_constraint", "*")),
            required=bool(value.get("required", True)),
            deprecated=bool(value.get("deprecated", False)),
        )
