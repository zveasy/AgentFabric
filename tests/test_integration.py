"""Integration test: install agent from path, run with stub, assert output."""

import asyncio
import json

from agentfabric.runtime.manifest import load_manifest
from agentfabric.runtime.orchestrator import Orchestrator


def test_install_and_run_flow(tmp_path):
    # Create a minimal agent dir with manifest
    agent_dir = tmp_path / "my_agent"
    agent_dir.mkdir()
    (agent_dir / "manifest.json").write_text(json.dumps({
        "name": "my_agent",
        "version": "1.0",
        "description": "Integration test agent",
    }))
    manifest = load_manifest(agent_dir / "manifest.json")
    orchestrator = Orchestrator()
    def runner(req):
        return {"type": "run_response", "id": "r1", "request_id": req["id"], "success": True, "output": {"received": req["input"]}, "error": None, "events": []}
    orchestrator.register_agent(manifest, runner)
    result = asyncio.run(orchestrator.run("my_agent", {"query": "hello"}))
    assert result["success"] is True
    assert result["output"]["received"]["query"] == "hello"
