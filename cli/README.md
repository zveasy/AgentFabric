# AgentFabric CLI

The CLI is installed with the `agentfabric` package:

```bash
pip install -e .
agentfabric list
agentfabric install /path/to/agent
agentfabric run my_agent '{"query": "hello"}'
```

Config file: `~/.agentfabric/config.json` or `AGENTFABRIC_CONFIG`. Options: `timeout_seconds`, `max_tool_calls`, `llm_endpoint` (reserved for future).

Exit codes: 0 success, 1 error, 2 not found.

See [CLI reference](../docs/cli-reference.md).
