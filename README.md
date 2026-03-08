# AgentFabric

Production-oriented scaffolding for AgentFabric phases 1-4.

## What is implemented

This repository now includes concrete, runnable implementations for all phases:

- **Phase 1 (Core Runtime)**:
  - Versioned protocol envelope with request/response/event/tool/capability messages.
  - Manifest loader + `manifest.v1` schema.
  - Runtime orchestrator lifecycle (`install -> load -> run -> suspend -> uninstall`).
  - Permission-enforced tool router and sandbox boundary checks.
  - Persistent scoped memory by `user/session/agent` with TTL retention.
  - Package integrity verifier, runtime-only secret store, structured logs, metrics, optional tracing.
  - SDK base class (`Agent`) and execution context for tool/memory/event access.
- **Phase 2 (Marketplace)**:
  - Registry service with publish + versioned package storage.
  - Publish pipeline checks: manifest validation and signature verification.
  - Discovery with search/category/permissions filters and pagination.
  - Ratings and moderation hooks.
  - Billing + metering queue with idempotent processing.
  - Tenant-scoped installs and namespace-level controls.
- **Phase 3 (Agent Collaboration)**:
  - Agent-to-agent delegate/handoff message contract.
  - Collaboration policy checks (who can call whom, timeout, quotas).
  - Workflow engine for DAG execution with retries and idempotent run keys.
  - Cross-node trace metadata emitted in workflow output.
- **Phase 4 (Enterprise)**:
  - RBAC role/permission enforcement (`admin`, `developer`, `viewer`).
  - Immutable audit log with hash chaining.
  - Private marketplace namespaces with explicit access grants.
  - SLA/support tier catalog.

## Layout

- `agentfabric/phase1/`: core runtime, protocol, SDK, sandbox, security, observability.
- `agentfabric/phase2/`: marketplace services.
- `agentfabric/phase3/`: collaboration protocol + workflow runtime.
- `agentfabric/phase4/`: enterprise controls.
- `agentfabric/cli.py`: lightweight CLI entrypoint.
- `agents/manifest_schema/manifest.v1.schema.json`: versioned manifest schema.
- `tests/`: unit/integration-style tests for phases 1-4.

## Quickstart

Run tests:

`python -m unittest discover -s tests -v`

Run the CLI:

`python -m agentfabric.cli --help`

## Runtime CLI lifecycle (Phase 1)

Example local lifecycle flow:

1. `agentfabric install --manifest /path/to/manifest.json --payload "artifact" --signer dev --key secret`
2. `agentfabric load --agent-id your.agent.id`
3. `agentfabric run --agent-id your.agent.id --user u1 --session s1 --request '{"prompt":"hello"}'`
4. `agentfabric suspend --agent-id your.agent.id`
5. `agentfabric uninstall --agent-id your.agent.id`
