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

## Production hardening implemented (P0, P1, P2)

- **P0 (must-have)**:
  - Durable SQLite persistence for registry, installs, billing events, runtime state, auth tokens, RBAC, namespaces, audit, moderation, compliance, and legal docs.
  - Hosted HTTP API (`agentfabric.production.api`) for health/auth/registry/runtime/billing/enterprise/compliance ops.
  - Token auth with expiry, rotation, service identities, and tenant/scope checks.
- **P1 (security/reliability)**:
  - Package security pipeline: signature policy, integrity verification, SBOM generation, malware scan hooks.
  - Sandbox hardening policy additions: denied filesystem prefixes and host egress allow-list.
  - Ops primitives: Prometheus exporter, trace exporter, backup/restore manager, retry worker.
- **P2 (marketplace/compliance)**:
  - Review moderation queue and admin resolution workflow.
  - Payment gateway abstraction (mock + Stripe adapter hook) and settlement ledger writes.
  - GDPR deletion request/processor, SIEM audit export, and legal document publish/acceptance tracking.

## Layout

- `agentfabric/phase1/`: core runtime, protocol, SDK, sandbox, security, observability.
- `agentfabric/phase2/`: marketplace services.
- `agentfabric/phase3/`: collaboration protocol + workflow runtime.
- `agentfabric/phase4/`: enterprise controls.
- `agentfabric/production/`: durable control-plane, API server, and production ops modules.
- `agentfabric/cli.py`: lightweight CLI entrypoint.
- `agents/manifest_schema/manifest.v1.schema.json`: versioned manifest schema.
- `tests/`: unit/integration-style tests for phases 1-4.

## Quickstart

Run tests:

`python -m unittest discover -s tests -v`

Run the CLI:

`python -m agentfabric.cli --help`

Run production API:

`python -m agentfabric.cli prod-api --db-path agentfabric.db --host 127.0.0.1 --port 8080`

## Runtime CLI lifecycle (Phase 1)

Example local lifecycle flow:

1. `agentfabric install --manifest /path/to/manifest.json --payload "artifact" --signer dev --key secret`
2. `agentfabric load --agent-id your.agent.id`
3. `agentfabric run --agent-id your.agent.id --user u1 --session s1 --request '{"prompt":"hello"}'`
4. `agentfabric suspend --agent-id your.agent.id`
5. `agentfabric uninstall --agent-id your.agent.id`
