"""Unit tests for manifest loading and validation."""

import json
import tempfile
from pathlib import Path

import pytest

from agentfabric.runtime.manifest import Manifest, load_manifest


VALID_MANIFEST = {
    "name": "test_agent",
    "version": "1.0",
    "description": "A test agent",
    "permissions": ["read_data"],
    "tools": ["tool_a"],
}


def test_load_manifest_from_json(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(VALID_MANIFEST))
    m = load_manifest(path)
    assert m.name == "test_agent"
    assert m.version == "1.0"
    assert m.permissions == ["read_data"]
    assert m.tools == ["tool_a"]
    assert m.allows_tool("tool_a") is True
    assert m.allows_tool("tool_b") is False


def test_load_manifest_from_yaml(tmp_path):
    import yaml
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.dump(VALID_MANIFEST))
    m = load_manifest(path)
    assert m.name == "test_agent"


def test_manifest_missing_required_raises(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"name": "x"}))  # missing version, description
    with pytest.raises(Exception):  # jsonschema.ValidationError
        load_manifest(path)


def test_manifest_invalid_name_pattern(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({**VALID_MANIFEST, "name": "Invalid-Name"}))  # pattern ^[a-z][a-z0-9_]*$
    with pytest.raises(Exception):
        load_manifest(path)


def test_manifest_allows_permission():
    m = Manifest(VALID_MANIFEST)
    assert m.allows_permission("read_data") is True
    assert m.allows_permission("write_data") is False
