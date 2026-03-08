# AgentFabric Python SDK

The SDK is provided by the `agentfabric` package. Install from the repo:

```bash
pip install -e .
```

Then:

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
            True,
            output={"result": f"Processed: {query}"},
        )
```

See [SDK guide](../docs/sdk-guide.md) and [README](../../README.md).
