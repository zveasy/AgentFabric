"""Unit tests for audit log and verification."""

import json
import tempfile
from pathlib import Path

from agentfabric.runtime.audit import AuditLog
from agentfabric.runtime.verification import compute_package_digest, verify_signature


def test_audit_log_to_file(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    audit = AuditLog(path=log_path)
    audit.log_install("agent1", "1.0", "/path/to/agent", True)
    audit.log_permission_denied("req-1", "agent1", "tool_x", "not in manifest")
    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 2
    e1 = json.loads(lines[0])
    assert e1["event"] == "install"
    assert e1["agent_id"] == "agent1"
    e2 = json.loads(lines[1])
    assert e2["event"] == "permission_denied"
    assert e2["tool_or_resource"] == "tool_x"


def test_verify_signature_no_file(tmp_path):
    manifest = {"name": "a", "version": "1.0", "description": "d"}
    valid, err = verify_signature(tmp_path, manifest)
    assert valid is True
    assert err is None


def test_verify_signature_digest_mismatch(tmp_path):
    (tmp_path / ".agentfabric").mkdir(parents=True)
    (tmp_path / ".agentfabric" / "signature.json").write_text(json.dumps({"digest": "wrong"}))
    manifest = {"name": "a", "version": "1.0", "description": "d"}
    valid, err = verify_signature(tmp_path, manifest)
    assert valid is False
    assert "mismatch" in (err or "")


def test_compute_package_digest(tmp_path):
    (tmp_path / "manifest.json").write_text('{"name":"x","version":"1.0","description":"d"}')
    manifest = {"name": "x", "version": "1.0", "description": "d"}
    d1 = compute_package_digest(manifest, tmp_path)
    d2 = compute_package_digest(manifest, tmp_path)
    assert d1 == d2
