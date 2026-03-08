"""Unit tests for the tool router and permission checks."""

import asyncio

import pytest

from agentfabric.runtime.manifest import Manifest
from agentfabric.runtime.routing import ToolRouter


MANIFEST_WITH_TOOLS = Manifest({
    "name": "test_agent",
    "version": "1.0",
    "description": "Test",
    "permissions": ["read_data"],
    "tools": ["allowed_tool"],
})


@pytest.fixture
def router():
    r = ToolRouter()
    r.register_tool("allowed_tool", lambda name, args: {"result": args})
    return r


def test_can_execute_allowed(router):
    allowed, err = router.can_execute(MANIFEST_WITH_TOOLS, "allowed_tool")
    assert allowed is True
    assert err is None


def test_can_execute_not_in_manifest(router):
    allowed, err = router.can_execute(MANIFEST_WITH_TOOLS, "other_tool")
    assert allowed is False
    assert "not in manifest" in (err or "")


def test_can_execute_no_executor():
    r = ToolRouter()
    m = MANIFEST_WITH_TOOLS
    allowed, err = r.can_execute(m, "allowed_tool")
    assert allowed is False
    assert "no registered executor" in (err or "")


@pytest.mark.asyncio
async def test_execute_success(router):
    call = {"id": "c1", "name": "allowed_tool", "arguments": {"x": 1}}
    result = await router.execute(call, MANIFEST_WITH_TOOLS, "req-1")
    assert result["success"] is True
    assert result["data"] == {"x": 1}


@pytest.mark.asyncio
async def test_execute_permission_denied(router):
    call = {"id": "c1", "name": "forbidden_tool", "arguments": {}}
    result = await router.execute(call, MANIFEST_WITH_TOOLS, "req-1")
    assert result["success"] is False
    assert result["error"]["code"] == "permission_denied"
