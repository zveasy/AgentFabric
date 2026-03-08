# Security Model

AgentFabric enforces a deny-by-default security model for agents.

## What Agents Cannot Do

- **Arbitrary filesystem**: No access to host files unless the runtime exposes it via a tool (e.g. read_file declared in manifest and implemented by the runtime).
- **Arbitrary network**: No outbound calls unless a tool provides it and is declared in the manifest.
- **System agents**: Agents cannot modify or replace other installed agents or runtime code.
- **Secrets in code**: Secrets must not appear in manifests or agent source; they are injected by the runtime (e.g. via environment or a secrets API).

## What Agents Must Declare

- **permissions**: Scopes the agent is allowed to use (e.g. `read_market_data`, `write_reports`). Every tool or resource access is checked against this list.
- **tools**: Names of tools the agent may invoke. The runtime denies any tool call not in this list.
- **Memory and data**: Use of persistent memory is scoped per user/session/agent; agents cannot read other scopes.

The runtime enforces these rules at run time. Permission denials are logged in the audit log.

## Package Integrity

- Agent packages can be **signed**. The runtime verifies digest (and optionally signature) at install and load. Unsigned packages can be allowed in dev; production policy can require signing.
- Audit log records installs and uninstalls for traceability.

## Audit Logging

Security-relevant events are written to an append-only audit log (file or stream): install, uninstall, run_started, run_completed, permission_denied, sandbox_event. See `agentfabric.runtime.audit.AuditLog`.

## Sandbox

Agents run in a controlled environment (subprocess or restricted in-process). The sandbox does not pass through arbitrary environment variables; only runtime-injected env (e.g. `AGENTFABRIC_AGENT_ID`, `AGENTFABRIC_SECRET_*`) is available. Timeouts and max tool calls limit resource use.

## API / Protocol Versioning

- Protocol version is carried in messages (`protocol: "v1"`). Backward-incompatible changes will bump the major version.
- Runtimes SHOULD support at least the current and previous major version (N-1). See [Agent Protocol Layer](agent-protocol-layer.md#versioning-and-compatibility).
