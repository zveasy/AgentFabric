# CLI Reference

The `agentfabric` CLI is installed with the Python package. Config and data paths can be overridden with environment variables.

## Commands

### `agentfabric list`

List installed agents (name, version, description).

- **Exit code**: 0
- **Data**: Reads from `AGENTFABRIC_AGENTS_DIR` (default `~/.agentfabric/agents`).

### `agentfabric install <path>`

Install an agent from a local directory. The directory must contain `manifest.yaml` or `manifest.json`. Package integrity is verified if a signature is present.

- **Exit code**: 0 on success, 1 on error (invalid manifest, verification failure), 2 if path not found.
- **Example**: `agentfabric install ./my_agent`

### `agentfabric run <agent_id> [input]`

Run an agent by id. Optional `input` is JSON or a single string (treated as `{"query": "<input>"}`).

- **Exit code**: 0 on success, 1 on run error, 2 if agent not found.
- **Output**: On success, prints the agent output as JSON to stdout. Errors go to stderr.
- **Example**: `agentfabric run my_agent '{"query": "hello"}'`

## Config File

Path: `~/.agentfabric/config.json` or set `AGENTFABRIC_CONFIG`.

Options:

| Key | Description | Default |
|-----|-------------|---------|
| `timeout_seconds` | Max run duration (seconds) | 60 |
| `max_tool_calls` | Max tool calls per run | 20 |
| `llm_endpoint` | Reserved for future LLM backend | — |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AGENTFABRIC_CONFIG` | Path to config JSON. |
| `AGENTFABRIC_AGENTS_DIR` | Directory for installed agents. |
| `AGENTFABRIC_AUDIT_LOG` | Path for audit log file (JSON lines). |

## Exit Codes

- **0** — Success
- **1** — Error (usage, validation, run failure)
- **2** — Not found (agent or path)
