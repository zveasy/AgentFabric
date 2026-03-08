# SDK Guide

Use the AgentFabric Python SDK to build agents that run on the AgentFabric runtime.

## Install

From the repo:

```bash
pip install -e .
```

## Minimal Agent

```python
from agentfabric import Agent
from agentfabric.runtime import load_manifest

class MyAgent(Agent):
    def __init__(self):
        super().__init__(manifest_path="manifest.yaml")

    def run(self, request):
        query = request.get("input", {}).get("query", "")
        return self.run_response(
            request["id"],
            success=True,
            output={"result": f"Processed: {query}"},
        )
```

- `request` is the protocol `run_request` (has `id`, `input`, `options` with `correlation_id`, etc.).
- Return a protocol `run_response`. Use `Agent.run_response(request_id, success, output=..., error=..., events=...)` to build it.

## Using Tools

If the runtime injects a tool router and the agent declares `tools` in the manifest:

```python
def run(self, request):
    tool_router = request.get("options", {}).get("tool_router")  # if provided by runtime
    if tool_router:
        data = self.run_tool_sync("my_tool", {"arg": "value"}, tool_router, request["id"])
    return self.run_response(request["id"], True, output={"data": data})
```

## Manifest

Ship a `manifest.yaml` or `manifest.json` next to your code. See [Manifest Reference](manifest-reference.md).

## Publish and Run

- **Local run**: Put the agent directory under `~/.agentfabric/agents/` (or use `agentfabric install /path/to/agent`), then `agentfabric run my_agent '{"query":"hello"}'`.
- **Publish** (Phase 2): `agentfabric publish` will upload to the registry; for now use `agentfabric install` from a path.

## Protocol

Agents communicate via the [Agent Protocol Layer](agent-protocol-layer.md): run_request in, run_response out; tool_call/tool_result when using tools.
