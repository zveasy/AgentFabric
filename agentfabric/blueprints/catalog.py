"""Industry blueprint catalog."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


BLUEPRINT_CATEGORIES = {
    "fintech",
    "construction",
    "trust",
    "energy",
    "defense",
    "manufacturing",
    "robotics",
    "aerospace",
}


@dataclass(frozen=True)
class IndustryBlueprint:
    category: str
    version: str
    package_structure: tuple[str, ...]
    api_routes: tuple[str, ...]
    event_schemas: tuple[str, ...]
    persistence: tuple[str, ...]
    observability: tuple[str, ...]
    rbac_scopes: tuple[str, ...]
    quality_gates: dict[str, float]
    deployment_models: tuple[str, ...]

    def validate(self) -> None:
        if self.category not in BLUEPRINT_CATEGORIES:
            raise ValueError(f"unsupported blueprint category: {self.category}")
        if not self.package_structure or not self.quality_gates:
            raise ValueError("blueprint structure and quality gates are required")

    @property
    def blueprint_id(self) -> str:
        return f"industry-blueprint-{sha256(self.export_json().encode()).hexdigest()[:16]}"

    def as_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "version": self.version,
            "package_structure": list(self.package_structure),
            "api_routes": sorted(self.api_routes),
            "event_schemas": sorted(self.event_schemas),
            "persistence": sorted(self.persistence),
            "observability": sorted(self.observability),
            "rbac_scopes": sorted(self.rbac_scopes),
            "quality_gates": dict(sorted(self.quality_gates.items())),
            "deployment_models": sorted(self.deployment_models),
        }

    def export_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


class BlueprintCatalog:
    def __init__(self) -> None:
        self._items = {category: _default_blueprint(category) for category in sorted(BLUEPRINT_CATEGORIES)}

    def get(self, category: str) -> IndustryBlueprint:
        try:
            return self._items[category]
        except KeyError as exc:
            raise KeyError(f"blueprint not found: {category}") from exc

    def list(self) -> list[IndustryBlueprint]:
        return [self._items[key] for key in sorted(self._items)]


def _default_blueprint(category: str) -> IndustryBlueprint:
    blueprint = IndustryBlueprint(
        category=category,
        version="1.0.0",
        package_structure=("services/", "packages/", "apps/", "tests/", "docs/", "deploy/"),
        api_routes=(f"/{category}/health", f"/{category}/resources"),
        event_schemas=(f"{category}.resource.created", f"{category}.resource.updated"),
        persistence=("tenant_scoped_store", "durable_events"),
        observability=("metrics", "tracing", "health", "audit"),
        rbac_scopes=(f"{category}:read", f"{category}:write", f"{category}:admin"),
        quality_gates={
            "architecture_quality": 0.8,
            "code_quality": 0.8,
            "security_posture": 0.85,
            "test_coverage": 0.8,
        },
        deployment_models=("container", "kubernetes"),
    )
    blueprint.validate()
    return blueprint
