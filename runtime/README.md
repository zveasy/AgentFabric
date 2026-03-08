# Runtime

The AgentFabric runtime lives in the `agentfabric` Python package:

- **Orchestrator**: `agentfabric.runtime.orchestrator` — load agents, route run requests, timeouts
- **Sandbox**: `agentfabric.runtime.sandbox` — isolated execution
- **Tool router**: `agentfabric.runtime.routing` — permission-checked tool execution
- **Memory**: `agentfabric.runtime.memory` — scoped persistent storage

See [Agent Protocol Layer](../docs/agent-protocol-layer.md) and [Architecture](../docs/architecture.md).
