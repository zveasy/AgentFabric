"""Unit tests for the orchestrator."""

import asyncio

import pytest

from agentfabric.runtime.manifest import Manifest
from agentfabric.runtime.orchestrator import Orchestrator


VALID_MANIFEST = Manifest({
    "name": "echo_agent",
    "version": "1.0",
    "description": "Echo agent",
})


@pytest.fixture
def orchestrator():
    return Orchestrator(timeout_seconds=2.0, max_tool_calls_per_run=10)


def test_register_and_list(orchestrator):
    def runner(req):
        return {"type": "run_response", "id": "r1", "request_id": req["id"], "success": True, "output": req["input"], "error": None, "events": []}
    orchestrator.register_agent(VALID_MANIFEST, runner)
    agents = orchestrator.list_agents()
    assert agents == [("echo_agent", "1.0")]


def test_run_agent_not_found(orchestrator):
    result = asyncio.run(orchestrator.run("missing", {"q": "x"}))
    assert result["success"] is False
    assert result["error"]["code"] == "agent_not_found"


@pytest.mark.asyncio
async def test_run_success(orchestrator):
    def runner(req):
        return {"type": "run_response", "id": "r1", "request_id": req["id"], "success": True, "output": {"echo": req["input"]}, "error": None, "events": []}
    orchestrator.register_agent(VALID_MANIFEST, runner)
    result = await orchestrator.run("echo_agent", {"query": "hello"})
    assert result["success"] is True
    assert result["output"]["echo"]["query"] == "hello"


@pytest.mark.asyncio
async def test_run_timeout(orchestrator):
    def slow_runner(req):
        import time
        time.sleep(5)
        return {"type": "run_response", "request_id": req["id"], "success": True, "output": {}, "error": None, "events": []}
    orchestrator.register_agent(VALID_MANIFEST, slow_runner)
    result = await orchestrator.run("echo_agent", {}, timeout_seconds=0.1)
    assert result["success"] is False
    assert result["error"]["code"] == "timeout"


def test_unregister(orchestrator):
    orchestrator.register_agent(VALID_MANIFEST, lambda r: r)
    assert orchestrator.unregister_agent("echo_agent") is True
    assert orchestrator.unregister_agent("echo_agent") is False
    assert orchestrator.list_agents() == []
