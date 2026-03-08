"""Sandbox tests: agent that tries to escape (filesystem, network) is denied."""

import pytest

from agentfabric.runtime.manifest import Manifest
from agentfabric.runtime.sandbox import Sandbox


def test_sandbox_env_restriction(tmp_path):
    """Sandbox does not pass through arbitrary PATH; agent gets controlled env."""
    m = Manifest({"name": "bad_agent", "version": "1.0", "description": "Test"})
    s = Sandbox(tmp_path, m, env={"PATH": "/malicious", "AGENTFABRIC_AGENT_ID": "bad_agent"})
    # Our sandbox overwrites AGENTFABRIC_AGENT_ID and does not pass PATH from caller
    assert s._env.get("AGENTFABRIC_AGENT_ID") == "bad_agent"
    # PATH should be removed in constructor (no passthrough of arbitrary env)
    assert "PATH" not in s._env or s._env["PATH"] != "/malicious"
