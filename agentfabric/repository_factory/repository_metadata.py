"""Deterministic repository metadata and manifests."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json


REPOSITORY_TYPES = {
    "service",
    "library",
    "frontend",
    "cli",
    "edge",
    "infrastructure",
    "ai_agent",
    "domain_platform",
}


@dataclass(frozen=True)
class RepositoryManifest:
    name: str
    domain: str
    purpose: str
    architecture: str
    repository_type: str
    dependencies: tuple[str, ...] = ()
    apis: tuple[str, ...] = ()
    rbac_scopes: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    observability: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    documentation_requirements: tuple[str, ...] = ()
    package_structure: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    def validate(self) -> None:
        if not all((self.name, self.domain, self.purpose, self.architecture)):
            raise ValueError("repository manifest is missing required fields")
        if self.repository_type not in REPOSITORY_TYPES:
            raise ValueError(f"unsupported repository type: {self.repository_type}")
        if not self.tests or not self.documentation_requirements:
            raise ValueError("tests and documentation requirements are mandatory")

    @property
    def repository_id(self) -> str:
        return f"repo-{sha256(self.export_json().encode()).hexdigest()[:16]}"

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "domain": self.domain,
            "purpose": self.purpose,
            "architecture": self.architecture,
            "repository_type": self.repository_type,
            "dependencies": sorted(self.dependencies),
            "apis": sorted(self.apis),
            "rbac_scopes": sorted(self.rbac_scopes),
            "events": sorted(self.events),
            "observability": sorted(self.observability),
            "tests": sorted(self.tests),
            "documentation_requirements": sorted(self.documentation_requirements),
            "package_structure": list(self.package_structure),
            "metadata": dict(sorted(self.metadata.items())),
        }

    def export_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "RepositoryManifest":
        return cls(
            name=str(value["name"]),
            domain=str(value["domain"]),
            purpose=str(value["purpose"]),
            architecture=str(value["architecture"]),
            repository_type=str(value["repository_type"]),
            dependencies=tuple(str(item) for item in value.get("dependencies", ())),
            apis=tuple(str(item) for item in value.get("apis", ())),
            rbac_scopes=tuple(str(item) for item in value.get("rbac_scopes", ())),
            events=tuple(str(item) for item in value.get("events", ())),
            observability=tuple(str(item) for item in value.get("observability", ())),
            tests=tuple(str(item) for item in value.get("tests", ())),
            documentation_requirements=tuple(str(item) for item in value.get("documentation_requirements", ())),
            package_structure=tuple(str(item) for item in value.get("package_structure", ())),
            metadata=dict(value.get("metadata", {})),
        )
