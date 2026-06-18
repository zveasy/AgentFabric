"""
Manifest loading and validation against the AgentFabric manifest schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "manifest.v1.schema.json"
# Fallback for repo layout when not installed
if not _SCHEMA_PATH.exists():
    _SCHEMA_PATH = Path(__file__).resolve().parents[2] / "agents" / "manifest_schema" / "manifest.v1.schema.json"


def _load_schema() -> dict[str, Any]:
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_manifest(path: str | Path) -> "Manifest":
    """Load and validate a manifest from a YAML or JSON file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")
    raw = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)
    return Manifest(data)


class Manifest:
    """Validated agent manifest (v1)."""

    def __init__(self, data: dict[str, Any]) -> None:
        schema = _load_schema()
        jsonschema.validate(instance=data, schema=schema)
        self._data = data

    @property
    def name(self) -> str:
        return self._data["name"]

    @property
    def version(self) -> str:
        return self._data["version"]

    @property
    def description(self) -> str:
        return self._data["description"]

    @property
    def permissions(self) -> list[str]:
        return self._data.get("permissions") or []

    @property
    def tools(self) -> list[str]:
        return self._data.get("tools") or []

    @property
    def inputs(self) -> list[str]:
        return self._data.get("inputs") or []

    @property
    def outputs(self) -> list[str]:
        return self._data.get("outputs") or []

    @property
    def entrypoint(self) -> str | None:
        return self._data.get("entrypoint")

    @property
    def raw(self) -> dict[str, Any]:
        return dict(self._data)

    def allows_tool(self, tool_name: str) -> bool:
        """Return True if the manifest allows use of the given tool."""
        return tool_name in self.tools

    def allows_permission(self, permission: str) -> bool:
        """Return True if the manifest has the given permission."""
        return permission in self.permissions
