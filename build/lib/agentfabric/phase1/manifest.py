"""Agent manifest model and validation helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentfabric.errors import ValidationError


@dataclass(frozen=True)
class AgentManifest:
    manifest_version: str
    agent_id: str
    name: str
    description: str
    version: str
    entrypoint: str
    capabilities: tuple[str, ...]
    permissions: tuple[str, ...]
    sandbox: dict[str, Any]
    max_run_seconds: float = 60.0
    max_tool_calls: int = 16


class ManifestLoader:
    """Loads and validates v1 agent manifests."""

    REQUIRED_FIELDS = {
        "manifest_version",
        "agent_id",
        "name",
        "description",
        "version",
        "entrypoint",
        "capabilities",
        "permissions",
        "sandbox",
    }

    def from_dict(self, payload: dict[str, Any]) -> AgentManifest:
        missing = sorted(self.REQUIRED_FIELDS.difference(payload.keys()))
        if missing:
            raise ValidationError(f"manifest missing fields: {', '.join(missing)}")
        if payload["manifest_version"] != "v1":
            raise ValidationError("manifest_version must be v1")
        if not isinstance(payload.get("capabilities"), list):
            raise ValidationError("manifest.capabilities must be a list")
        if not isinstance(payload.get("permissions"), list):
            raise ValidationError("manifest.permissions must be a list")
        if not isinstance(payload.get("sandbox"), dict):
            raise ValidationError("manifest.sandbox must be an object")
        return AgentManifest(
            manifest_version=payload["manifest_version"],
            agent_id=payload["agent_id"],
            name=payload["name"],
            description=payload["description"],
            version=payload["version"],
            entrypoint=payload["entrypoint"],
            capabilities=tuple(payload["capabilities"]),
            permissions=tuple(payload["permissions"]),
            sandbox=payload["sandbox"],
            max_run_seconds=float(payload.get("max_run_seconds", 60.0)),
            max_tool_calls=int(payload.get("max_tool_calls", 16)),
        )

    def from_file(self, path: str | Path) -> AgentManifest:
        return self.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
