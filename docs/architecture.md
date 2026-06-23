# Architecture Overview

AgentFabric sits between user interfaces / applications and one or more LLMs. It provides a single runtime that loads agents from manifests, routes requests, enforces permissions, and runs agent code in a sandbox.

## High-Level Diagram

```
User / App
    |
    v
AgentFabric Runtime
    |-- Orchestrator (route by agent_id, timeouts)
    |-- Tool Router (permission check, dispatch to executors)
    |-- Sandbox (isolated execution per agent)
    |-- Memory (scoped key-value store)
    |-- Audit Log (install, run, permission_denied, sandbox events)
    v
Installed Agents (manifests + code)
    |
    v
LLM / Model (optional; agents can call tools only)
```

## Components

- **Orchestrator**: Registers agents by manifest, dispatches run requests by `agent_id`, applies timeouts and max tool calls. Returns protocol `run_response`.
- **Tool Router**: Validates each tool call against the agent manifest (`tools` and `permissions`). Dispatches to registered executors; returns protocol `tool_result`.
- **Sandbox**: Runs agent code in a restricted environment (subprocess or in-process). Injects only declared env; no arbitrary filesystem/network unless provided via tools.
- **Memory**: Per-user, per-session, per-agent key-value store for persistent state. Used by agents via tools or SDK.
- **Audit Log**: Append-only log of installs, runs, permission denials, sandbox events. For security and debugging.

## Data Flow

1. User or app sends a run request (agent_id + input).
2. Orchestrator looks up the agent, builds a protocol `run_request`, and invokes the agent runner (sync or async).
3. If the agent calls a tool, the runtime receives a `tool_call`, checks manifest, executes via Tool Router, returns `tool_result`.
4. Agent returns a `run_response` (success + output or error).
5. Orchestrator returns the response to the caller. Metrics and audit events are recorded.

## Protocol

All messages follow the [Agent Protocol Layer](agent-protocol-layer.md): JSON wire format, versioned (`v1`), with defined types for run_request, tool_call, tool_result, run_response, and events.

## Deployment

- **Local**: CLI `agentfabric run` and Python API; agents live under `~/.agentfabric/agents/` (or `AGENTFABRIC_AGENTS_DIR`).
- **Hosted** (Phase 2): Registry, API, and billing sit in front of the same runtime; orchestration can be distributed with a shared registry and queue.
# AgentFabric Architecture

AgentFabric is an enterprise agent operating system and AI Software Foundry.

## Foundry Layer

The software foundry sits above the runtime, governance, marketplace, connector, persistence, and evaluation layers:

```text
Idea
  -> Domain Blueprint + Knowledge Pack
  -> Repository Manifest
  -> Signed Generation Artifacts
  -> Repository Quality Gate
  -> Repository Package
  -> Lifecycle + Lineage + Marketplace
```

Repository manifests are canonical and content-addressed. Operational records remain tenant-scoped and event-sourced. Generation cannot proceed without complete quality evidence, and all generated artifacts, releases, updates, and lifecycle operations are included in audit exports.

The foundry consumes existing AgentFabric capabilities rather than bypassing them:

* persistence and event integrity from the durable state layer
* tenant context and RBAC from enterprise controls
* quality enforcement from evaluation
* package categories and release controls from marketplace
* audit export from the audit bundle
* VEIL and Aegis authority boundaries remain unchanged
# Generation 18: Controlled Repository Execution

The software foundry now has a distinct execution boundary. `repository_materializer` produces deterministic in-memory artifacts, while `repository_execution` owns tenant-scoped plans, quality gates, approvals, durable events, contained filesystem writes, replay verification, and rollback. This boundary prevents repository definition from implicitly causing filesystem side effects.

# Generation 19: Controlled Build Workers

`build_workers` consumes only completed approved repository executions. Capability-scoped workers generate a deterministic product delta, tests, documentation, quality evidence, and security evidence. A separate approval binds the output hashes before writes occur. Rollback restores exact pre-build contents, and audit exports retain hashes and decisions without source contents.

# Generation R1: RenovationOS Foundation

`verticals.renovation` is the first vertical product package. It uses canonical serializable models, local versioned cost assumptions, versioned JSON templates, tenant-scoped persistence, and hash-chained events to create estimates and proposals without network or AI-provider dependencies. Persisted inputs support exact replay and audit export.

# Generation R2: RenovationOS Operations

The renovation vertical now carries accepted proposals into job execution. `jobs` owns phased job state, `documentation` owns deterministic daily logs, notes, photo metadata, issues, and summaries, and `change_orders` reuses estimate assumptions for price adjustments and approval-ready documents. The facade enforces tenant ownership and reconstructs complete project histories for replay and audit.
