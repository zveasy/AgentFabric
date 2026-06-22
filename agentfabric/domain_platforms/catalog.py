"""Domain platform definitions and catalog."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


PLATFORM_NAMES = {
    "RenovationOS",
    "TreasuryOS",
    "TrustOS",
    "EnergyOS",
    "ManufacturingOS",
    "DefenseOS",
    "SpaceOS",
}


@dataclass(frozen=True)
class DomainPlatformDefinition:
    name: str
    version: str
    capabilities: tuple[str, ...]
    package_graph: dict[str, tuple[str, ...]]
    apis: tuple[str, ...]
    dependencies: tuple[str, ...]
    quality_gates: dict[str, float]
    deployment_targets: tuple[str, ...]
    required_evidence: tuple[str, ...]

    def validate(self) -> None:
        if self.name not in PLATFORM_NAMES:
            raise ValueError(f"unsupported domain platform: {self.name}")
        if not self.package_graph or not self.required_evidence:
            raise ValueError("platform package graph and evidence are required")

    @property
    def platform_id(self) -> str:
        return f"platform-{sha256(self.export_json().encode()).hexdigest()[:16]}"

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "capabilities": sorted(self.capabilities),
            "package_graph": {key: sorted(value) for key, value in sorted(self.package_graph.items())},
            "apis": sorted(self.apis),
            "dependencies": sorted(self.dependencies),
            "quality_gates": dict(sorted(self.quality_gates.items())),
            "deployment_targets": sorted(self.deployment_targets),
            "required_evidence": sorted(self.required_evidence),
        }

    def export_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "DomainPlatformDefinition":
        return cls(
            name=str(value["name"]),
            version=str(value.get("version", "1.0.0")),
            capabilities=tuple(str(item) for item in value.get("capabilities", ())),
            package_graph={
                str(key): tuple(str(item) for item in items)
                for key, items in dict(value.get("package_graph", {})).items()
            },
            apis=tuple(str(item) for item in value.get("apis", ())),
            dependencies=tuple(str(item) for item in value.get("dependencies", ())),
            quality_gates={str(key): float(item) for key, item in dict(value.get("quality_gates", {})).items()},
            deployment_targets=tuple(str(item) for item in value.get("deployment_targets", ())),
            required_evidence=tuple(str(item) for item in value.get("required_evidence", ())),
        )


class DomainPlatformCatalog:
    def __init__(self) -> None:
        self._platforms = {name: _platform(name) for name in sorted(PLATFORM_NAMES)}

    def register(self, platform: DomainPlatformDefinition) -> DomainPlatformDefinition:
        platform.validate()
        self._platforms[platform.name] = platform
        return platform

    def get(self, name: str) -> DomainPlatformDefinition:
        try:
            return self._platforms[name]
        except KeyError as exc:
            raise KeyError(f"platform not found: {name}") from exc

    def list(self) -> list[DomainPlatformDefinition]:
        return [self._platforms[key] for key in sorted(self._platforms)]


def _platform(name: str) -> DomainPlatformDefinition:
    if name == "RenovationOS":
        packages = {
            "reno_estimator": (),
            "change_order_agent": ("reno_estimator",),
            "contractor_command_center": ("change_order_agent", "materials_intelligence"),
            "materials_intelligence": (),
            "field_photo_intelligence": (),
            "reno_finance": ("reno_estimator", "change_order_agent"),
            "homeowner_portal": ("contractor_command_center", "reno_finance"),
            "reno_trust": ("change_order_agent", "field_photo_intelligence"),
            "reno_agentfabric": ("reno_trust", "contractor_command_center"),
        }
    else:
        slug = name.removesuffix("OS").lower()
        packages = {f"{slug}_core": (), f"{slug}_analytics": (f"{slug}_core",), f"{slug}_portal": (f"{slug}_core",)}
    platform = DomainPlatformDefinition(
        name=name,
        version="1.0.0",
        capabilities=("planning", "operations", "analytics", "governance"),
        package_graph=packages,
        apis=(f"/{name.lower()}/resources", f"/{name.lower()}/reports"),
        dependencies=("AgentFabric", "VEIL", "Aegis Gate"),
        quality_gates={
            "architecture_quality": 0.8,
            "test_coverage": 0.8,
            "security_posture": 0.9,
            "observability_readiness": 0.85,
        },
        deployment_targets=("docker", "kubernetes"),
        required_evidence=("test_results", "security_review", "event_integrity", "VEIL_audit_refs"),
    )
    platform.validate()
    return platform
