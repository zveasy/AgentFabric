"""Repository manifest builder."""

from __future__ import annotations

from .package_structure import build_package_structure
from .project_templates import project_template
from .repository_metadata import RepositoryManifest


class ManifestBuilder:
    def build(self, payload: dict[str, object]) -> RepositoryManifest:
        repository_type = str(payload.get("repository_type", "service"))
        template = project_template(repository_type)
        name = str(payload["name"])
        manifest = RepositoryManifest(
            name=name,
            domain=str(payload.get("domain", "general")),
            purpose=str(payload["purpose"]),
            architecture=str(payload.get("architecture", template["architecture"])),
            repository_type=repository_type,
            dependencies=tuple(str(item) for item in payload.get("dependencies", ())),
            apis=tuple(str(item) for item in payload.get("apis", ())),
            rbac_scopes=tuple(str(item) for item in payload.get("rbac_scopes", ())),
            events=tuple(str(item) for item in payload.get("events", ())),
            observability=tuple(str(item) for item in payload.get("observability", ("health", "metrics", "tracing"))),
            tests=tuple(str(item) for item in payload.get("tests", ("unit", "integration"))),
            documentation_requirements=tuple(
                str(item) for item in payload.get("documentation_requirements", ("README", "architecture", "API"))
            ),
            package_structure=tuple(
                str(item) for item in payload.get("package_structure", build_package_structure(repository_type, name))
            ),
            metadata=dict(payload.get("metadata", {})),
        )
        manifest.validate()
        return manifest
