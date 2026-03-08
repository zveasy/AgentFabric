# Agent Protocol Layer

This document defines the **AgentFabric Agent Protocol**: the interoperability standard between the runtime, agents, and LLM backends. It enables any compliant runtime to run any compliant agent.

---

## Why It Matters

The Agent Protocol Layer is the **TCP/IP of AI agents**: a shared contract so that:

- Any runtime can run any compliant agent
- Any agent can be published once and run anywhere
- Orchestration, tools, memory, and permissions are defined in a way that doesn't tie the ecosystem to one implementation

Without a well-designed protocol layer, you get walled gardens. With it, you get composable intelligence at scale.

---

## Wire Format

- **Primary format**: JSON (UTF-8). All message bodies are JSON objects.
- **Schema**: Message types are defined by JSON Schema; see [manifest schema](../agents/manifest_schema/) and the schemas below.
- **Protocol version**: Carried in header `X-AgentFabric-Protocol: v1` or in envelope field `"protocol": "v1"`. Runtimes MUST support the version they implement and MAY support N-1 for compatibility.

---

## Message Types

### 1. Run Request (Runtime → Agent / LLM)

Issued by the runtime when a user or upstream agent requests work.

```json
{
  "type": "run_request",
  "id": "req-uuid",
  "protocol": "v1",
  "agent_id": "financial_analysis_agent",
  "agent_version": "1.0",
  "input": { "query": "Forecast Q3 revenue", "context": {} },
  "options": {
    "timeout_seconds": 60,
    "max_tool_calls": 20,
    "correlation_id": "corr-uuid"
  }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | `"run_request"` |
| `id` | Yes | Unique request ID (UUID or similar) |
| `protocol` | Yes | Protocol version, e.g. `"v1"` |
| `agent_id` | Yes | Agent identifier from manifest |
| `agent_version` | No | Semantic version; used for routing and compatibility |
| `input` | Yes | Agent-specific input (query, context, etc.) |
| `options` | No | `timeout_seconds`, `max_tool_calls`, `correlation_id` for tracing |

### 2. Tool Call (Agent → Runtime)

Agent requests the runtime to execute a tool. The runtime enforces permissions and returns a Tool Result.

```json
{
  "type": "tool_call",
  "id": "call-uuid",
  "request_id": "req-uuid",
  "name": "market_api",
  "arguments": { "symbol": "AAPL", "range": "1d" }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | `"tool_call"` |
| `id` | Yes | Unique call ID |
| `request_id` | Yes | Parent run request ID |
| `name` | Yes | Tool name (must be declared in manifest `tools`) |
| `arguments` | Yes | JSON object of tool arguments |

### 3. Tool Result (Runtime → Agent)

Returned to the agent after the runtime executes (or denies) a tool call.

```json
{
  "type": "tool_result",
  "id": "result-uuid",
  "call_id": "call-uuid",
  "request_id": "req-uuid",
  "success": true,
  "data": { "price": 150.25, "volume": 1000000 },
  "error": null
}
```

Or on permission denied / failure:

```json
{
  "type": "tool_result",
  "id": "result-uuid",
  "call_id": "call-uuid",
  "request_id": "req-uuid",
  "success": false,
  "data": null,
  "error": { "code": "permission_denied", "message": "Tool 'market_api' not in manifest permissions" }
}
```

### 4. Run Response (Agent → Runtime)

Final outcome of a run.

```json
{
  "type": "run_response",
  "id": "resp-uuid",
  "request_id": "req-uuid",
  "success": true,
  "output": { "forecast": 1.2e9, "risk_assessment": "low" },
  "error": null,
  "events": []
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | `"run_response"` |
| `id` | Yes | Unique response ID |
| `request_id` | Yes | Corresponding run request ID |
| `success` | Yes | Whether the run completed successfully |
| `output` | No | Agent-defined result (must match manifest `outputs` semantics) |
| `error` | No | If `success` is false, error code and message |
| `events` | No | Optional list of audit/observability events |

### 5. Events (Streaming / Logging)

Used for progress, audit, and observability. Can be emitted during a run.

```json
{
  "type": "event",
  "name": "run_started",
  "request_id": "req-uuid",
  "timestamp": "2025-03-07T12:00:00Z",
  "payload": {}
}
```

Common event names: `run_started`, `run_completed`, `tool_call_started`, `tool_call_completed`, `permission_denied`, `sandbox_event`.

---

## Capability Discovery

- **Manifest**: Each agent package includes a manifest (see [Manifest Schema](../agents/manifest_schema/manifest.v1.schema.json)). The runtime loads the manifest at install and at load time.
- **Capabilities**: The manifest declares `name`, `version`, `permissions`, `inputs`, `outputs`, `tools`. The runtime uses this to:
  - Route run requests to the correct agent
  - Validate tool calls against `tools` and `permissions`
  - Validate input/output shapes (optional, implementation-specific)
- **Discovery API**: For marketplace/registry, agents are listed and retrieved by `agent_id` and optional `version`; the manifest is the source of truth for capabilities.

---

## Tool Invocation Contract

1. Agent sends **Tool Call** (name + arguments) to the runtime.
2. Runtime checks: (a) `name` is in manifest `tools`, (b) call is allowed by manifest `permissions`. If not, return **Tool Result** with `success: false` and `error.code: "permission_denied"` or `"invalid_tool"`.
3. Runtime executes the tool in the execution layer (sandbox or permitted environment), with optional timeout.
4. Runtime returns **Tool Result** with `success` and either `data` or `error`.
5. Agent continues until it produces a **Run Response**.

Secrets are never part of the tool call; the runtime injects them (e.g. via environment or a secure secrets API) when executing the tool.

---

## Agent Lifecycle

| State | Description | What crosses the sandbox boundary |
|-------|-------------|-----------------------------------|
| **install** | Package is fetched, verified (signature), unpacked, manifest validated and stored. | Package bytes, signature; manifest and metadata stored by runtime. |
| **load** | Runtime loads agent code and manifest into memory; prepares sandbox (env, mounts). | Manifest, config, env (no secrets in manifest). |
| **run** | Run request is dispatched; agent may issue tool calls and receive tool results; agent returns run response. | Run request, tool calls, tool results, run response; events. |
| **suspend** | Run is paused (optional; for long-running or resumable agents). | State checkpoint (implementation-defined). |
| **uninstall** | Agent package and metadata are removed. | Deletion of agent data; audit log entry. |

**Security boundary**: The sandbox MUST prevent the agent from accessing the host filesystem, network (unless declared in manifest), or other processes except through the runtime's tool router. Only the runtime injects secrets into the execution environment.

---

## Agent-to-Agent Handoff (Phase 3)

*Reserved for Phase 3.* The protocol will be extended with:

- A standard way for one agent to delegate a sub-task to another (e.g. include `delegate_to_agent_id` in a run request or a new message type).
- Quotas and timeouts for delegated runs.
- Correlation IDs to trace a request across agents.

---

## Versioning and Compatibility

- **Protocol version**: `v1` is the first stable version. Backward-incompatible changes will increment the major version (e.g. `v2`).
- **Manifest schema**: Versioned via `$schema` URL or `manifest_version: "1"` in the manifest; see [manifest.v1.schema.json](../agents/manifest_schema/manifest.v1.schema.json).
- **Compatibility policy**: Runtimes SHOULD support at least the current and previous major protocol version (N-1). Agents built for `v1` continue to work on runtimes that support `v1`.

---

## Reference

- [Manifest Schema v1](../agents/manifest_schema/manifest.v1.schema.json)
- [Architecture Overview](architecture.md)
- [Security Model](security-model.md)
