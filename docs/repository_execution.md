# Repository Execution

Generation 18 turns deterministic repository blueprints into controlled filesystem output. It does not permit open-ended autonomous coding.

## Execution lifecycle

1. `POST /factory/execution/plan` loads a supported platform package definition and produces deterministic steps, artifact hashes, quality-gate results, marketplace metadata, and a rollback plan.
2. `POST /factory/execution/dry-run` regenerates the artifacts in memory and verifies deterministic equality. It does not write files.
3. `POST /factory/execution/approve` records the tenant, approver, timestamp, and approved plan digest.
4. `POST /factory/execution/run` verifies the approval and writes the approved artifacts beneath the configured tenant output directory.
5. `POST /factory/execution/rollback` removes only paths declared by the approved plan.

Plans can be replayed through `RepositoryExecutionEngine.replay()`. A replay must produce the same execution ID and hashes or it fails closed.

## Safety model

- Repository names and every artifact path are validated before use.
- Absolute paths and `..` traversal are rejected.
- Runtime outputs are namespaced as `<factory_output_root>/<tenant_id>/<repository_id>`.
- Writes require an approval whose digest matches the current plan.
- Failed writes remove artifacts created during that attempt.
- Repeated completed execution calls are idempotent.
- Cross-tenant plan, event, result, and artifact reads are rejected.
- Audit bundles contain plans, approvals, hashes, quality gates, results, and rollbacks, but not generated source contents.

## Quality gates

Execution validates name safety, path containment, template output, manifest completeness, dependencies, RBAC scopes, event declarations, documentation, tests, and deterministic replay. Any failed gate blocks execution.

## Events

Repository execution emits durable hash-chained events for planning, dry runs, approvals, step starts, step completion or failure, execution completion, replay, and rollback.

## Configuration

Set `AGENTFABRIC_FACTORY_OUTPUT_ROOT` to the root used for generated repositories. The default is `/tmp/agentfabric-generated`.
