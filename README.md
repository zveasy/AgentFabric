# AgentFabric

AgentFabric is an autonomous agent runtime and registry that talks to VEIL through APIs for trust, sanitization, policy checks, restore requests, tool verification, token issuance, and audit logging.

Generation 16 adds continuous agent operational intelligence: tenant-scoped metrics, health histories, drift and anomaly detection, version comparisons, degradation gates, and controlled improvement recommendations.

Generation 17 adds a permissioned enterprise connector runtime with versioned manifests, tenant enablement, credential references, policy gates, sandbox controls, durable execution audits, and marketplace connector review.

The Software Foundry phase evolves AgentFabric into an API-first repository and industry-platform factory with deterministic blueprints, signed generation artifacts, fail-closed repository quality gates, lifecycle tracking, lineage analysis, and RenovationOS seed packages.

Generation 18 adds approval-gated repository execution. AgentFabric can now plan, dry-run, approve, materialize, replay, and roll back deterministic repository builds while preserving tenant isolation and durable audit evidence.

Generation 19 adds controlled build workers that convert approved scaffolds into tested first-pass product logic. RenovationOS now includes a deterministic estimator, governed change-order lifecycle, and contractor operations/reliability logic.

Generation R1 adds the RenovationOS Foundation vertical: persisted, tenant-scoped estimate and professional proposal generation using local rate tables and versioned templates with no external AI dependency.

Generation R2 advances the vertical into active job operations with accepted-proposal conversion, phased jobs, daily logs, field notes, photo metadata, issue tracking, deterministic change orders, approvals, exports, and complete project history.

This repository now carries two parallel shapes:

- The existing `agentfabric/` implementation, kept intact for compatibility with the current test surface.
- A new Phase 0 standalone foundation aligned to the roadmap, built around top-level packages for runtime, registry, scheduler, orchestration, memory, evaluations, versioning, marketplace, connectors, and `veil_client`.

## Canonical implementation direction

The primary source of truth in this branch is the newer production server stack:

- Postgres-ready SQLAlchemy models + Alembic migrations.
- FastAPI service with JWT auth middleware and OpenAPI.
- Queue abstraction with Redis backend and deterministic in-memory fallback.
- Signing and payment adapters (cosign/stripe with local fallbacks).
- CI/CD workflows, Docker image build, and Kubernetes manifests.

## What is implemented

- **Phase 1 (Core Runtime)**: protocol envelopes, manifest loading, lifecycle orchestration, sandbox + tool permission checks, scoped memory, observability, and SDK primitives.
- **Phase 2 (Marketplace)**: registry publish/list/install flows, discovery filters, ratings/moderation hooks, metering, and tenant-scoped controls.
- **Phase 3 (Collaboration)**: delegation protocol, policy checks, workflow DAG execution, retry/idempotency support, and trace metadata propagation.
- **Phase 4 (Enterprise)**: RBAC, immutable audit chain, private namespaces, and SLA/support controls.

## Production hardening (P0/P1/P2)

- **P0**: durable persistence layer, auth/token lifecycle, migration-driven schema management, and service endpoints.
- **P1**: package security pipeline, stronger sandbox policies, metrics/traces, backup/restore, and retry worker support.
- **P2**: moderation queue + resolution, billing settlement pathways, GDPR flows, SIEM export, and legal document lifecycle.

## Roadmap-aligned foundation

- `runtime/`: agent execution contracts and runtime-facing models.
- `registry/`: agent metadata and registry contracts.
- `scheduler/`: task scheduling models and workflow dispatch contracts.
- `orchestration/`: multi-agent workflow state models.
- `memory/`: tenant-scoped memory policies and records.
- `evaluations/`: evaluation scorecards and publish gates.
- `versioning/`: version, fork, merge, and rollback models.
- `marketplace/`: listing, install, and visibility contracts.
- `connectors/`: external tool and system connector interfaces.
- `veil_client/`: the only allowed boundary for VEIL interactions.

## Existing implementation layout

- `agentfabric/phase1`, `agentfabric/phase2`, `agentfabric/phase3`, `agentfabric/phase4`: legacy phase implementations.
- `agentfabric/production`: control-plane services and durable operations modules.
- `agentfabric/server`: FastAPI app, auth, queue, DB/session, worker, and integrations.
- `agent_observability`: post-release agent metrics, health, drift, anomalies, degradation, version comparison, and recommendations.
- `agent_connectors`: secure connector manifests, registry, credential vault, execution policy, sandbox, and audit runtime.
- `agentfabric/repository_factory`: deterministic project templates, manifests, blueprints, dependency graphs, and scaffolding.
- `agentfabric/software_factory`: signed requirements-to-release repository generation pipeline.
- `agentfabric/domain_platforms`, `agentfabric/blueprints`, `agentfabric/domain_knowledge`: industry platform infrastructure.
- `agentfabric/repository_lifecycle`, `agentfabric/repository_graph`, `agentfabric/software_teams`: lifecycle, lineage, impact, and team coordination.
- `agentfabric/repository_execution`, `agentfabric/repository_materializer`: approved execution plans, safe artifact writes, deterministic RenovationOS source trees, replay, and rollback.
- `agentfabric/build_workers`: capability-scoped domain, service, API, test, documentation, quality, and security workers with build approval, replay, review, and rollback.
- `agentfabric/verticals/renovation`: offline deterministic renovation estimates, proposal templates, replay, exports, events, and marketplace metadata.
- `agentfabric/verticals/renovation/jobs`, `documentation`, `change_orders`: proposal-to-job execution, audit-ready field records, rate-based change orders, approvals, and project history.
- `agentfabric/verticals/renovation/scheduling`, `crews`, `deliveries`: dependency schedules, crew coordination, material tracking, conflict detection, delay analysis, and reproducible completion forecasts.
- `agentfabric/cli.py`: production-oriented CLI entrypoint.
- `agents/manifest_schema/manifest.v1.schema.json`: manifest schema.
- `tests`: runtime, production, API stack, and foundation tests.

## Quickstart

Run tests:

`python -m unittest discover -s tests -v`

Run lint + type checks:

`ruff check agentfabric runtime registry scheduler orchestration memory evaluations versioning marketplace connectors veil_client tests`

`mypy agentfabric runtime registry scheduler orchestration memory evaluations versioning marketplace connectors veil_client`

Run migrations:

`python -m agentfabric.cli db-migrate --database-url "postgresql+psycopg://agentfabric:agentfabric@localhost:5432/agentfabric"`

Run API:

`python -m agentfabric.cli api-run --database-url "postgresql+psycopg://agentfabric:agentfabric@localhost:5432/agentfabric" --redis-url "redis://localhost:6379/0" --jwt-secret "change-me" --bootstrap-token "bootstrap-dev" --host 0.0.0.0 --port 8000`

Run worker:

`python -m agentfabric.cli worker-run --database-url "postgresql+psycopg://agentfabric:agentfabric@localhost:5432/agentfabric" --redis-url "redis://localhost:6379/0" --queue-name default --queue-max-attempts 3`

Legacy command compatibility:

`python -m agentfabric.cli prod-api --db-path agentfabric.db --host 127.0.0.1 --port 8080`

## Production deployment

- **Secrets**: When `AGENTFABRIC_ENVIRONMENT=production`, the app will not start unless `AGENTFABRIC_JWT_SECRET` is set to a non-default value of at least 32 characters.
- **Readiness**: Use `GET /ready` for Kubernetes readiness probes (checks DB and Redis). Use `GET /health` for liveness.
- **CORS**: Set `AGENTFABRIC_CORS_ORIGINS` to a comma-separated list of allowed origins (e.g. `https://app.example.com,https://admin.example.com`). If unset, no cross-origin requests are allowed.
- **Rate limiting**: Auth endpoints (`/auth/principals/register`, `/auth/token/issue`) are limited to 20 requests per minute per client IP by default. Override with `AGENTFABRIC_RATE_LIMIT_AUTH_PER_MINUTE`.
- **Docker**: The image uses env vars for config. Set `AGENTFABRIC_DATABASE_URL`, `AGENTFABRIC_REDIS_URL`, and `AGENTFABRIC_JWT_SECRET` (and optionally `AGENTFABRIC_ENVIRONMENT=production` and `AGENTFABRIC_BOOTSTRAP_TOKEN`) when running the container.
- **Env preference**: For `api-run` and `worker-run`, if `AGENTFABRIC_DATABASE_URL`, `AGENTFABRIC_REDIS_URL`, or `AGENTFABRIC_JWT_SECRET` are set in the environment, they override the CLI defaults. This allows Kubernetes `envFrom` to supply config without duplicating values in the pod command.
- **Metrics**: Set `AGENTFABRIC_METRICS_PUBLIC=true` to expose `GET /metrics` (and `GET /metrics/prometheus`) without authentication for Prometheus scraping. When false, metrics require the `metrics.read` scope.
- **Backup/restore**: `POST /ops/backup` (create; scope `ops.backup.write`), `GET /ops/backups` (list; scope `ops.backup.read`), `POST /ops/restore` with body `{"backup_file": "path"}` (scope `ops.backup.write`). Admin role includes these scopes.
- **Logging**: Set `AGENTFABRIC_LOG_LEVEL` (default `INFO`) and `AGENTFABRIC_JSON_LOGS` (default `true`). At startup the app configures structlog; in production use JSON logs for aggregation. Each request is logged (method, path, status_code, duration_ms, client_ip, request_id, principal_id). Pass `X-Request-ID` to correlate or receive it back in the response.
- **Sandbox**: For stricter agent isolation use `SandboxPolicy.strict()` (no network, minimal filesystem, broader denied prefixes); see `agentfabric.phase1.sandbox`.

## Deployment artifacts

- GitHub Actions: `.github/workflows/ci.yml`, `.github/workflows/cd.yml`
- Container: `Dockerfile`, `docker-compose.yml`
- Kubernetes: `deploy/k8s/*`

## Operational intelligence

Agent observability APIs are available under `/observability/metrics` and `/agents/{agent_id}` for health, drift, anomalies, recommendations, and version comparison. Events use the `agent.metric.recorded`, `agent.health.changed`, `agent.drift.detected`, `agent.anomaly.detected`, `agent.degradation.detected`, `agent.recommendation.created`, and `agent.version.compared` types.

RBAC scopes are `observability:read`, `observability:write`, `health:read`, `drift:read`, `anomaly:read`, `recommendations:read`, and `recommendations:approve`.

See [docs/observability.md](docs/observability.md) for the health model, detection rules, recommendation lifecycle, and fail-closed marketplace behavior.

## Enterprise connectors

Connector execution uses `ConnectorExecutionService`; agents do not receive credentials or call adapters directly. The APIs cover registration, tenant enablement, execution, and credential create/rotate/revoke operations. Durable events record all lifecycle and policy decisions.

Marketplace manifests declare `connector_requirements` and `connector_permissions`. Publication fails closed for undeclared permissions, excessive permissions, unreviewed risky connectors, or low connector trust.

See [docs/connectors.md](docs/connectors.md) for architecture, security, credential handling, APIs, events, and marketplace review.

## AI Software Foundry

The foundry accepts tenant-scoped ideas, applies industry blueprints and knowledge packs, enforces repository quality evidence, emits signed stage artifacts, and packages validated repositories. Built-in platforms include RenovationOS, TreasuryOS, TrustOS, EnergyOS, ManufacturingOS, DefenseOS, and SpaceOS.

Factory APIs are exposed under `/factory`. RenovationOS package definitions are available under `platforms/renovation_os/`.

See [docs/software_foundry.md](docs/software_foundry.md) for architecture, deterministic exports, quality gates, platform catalogs, events, and API details.

## Repository execution

Repository execution APIs are exposed under `/factory/execution`. Planning and dry runs are in-memory; file writes require a tenant-scoped approval whose digest matches the plan. Generated runtime repositories are isolated under the configured tenant output directory.

The first materialized RenovationOS repositories are `reno_estimator`, `change_order_agent`, and `contractor_command_center`.

See [docs/repository_execution.md](docs/repository_execution.md) for the execution and safety model, and [docs/renovation_os_buildout.md](docs/renovation_os_buildout.md) for the reference repositories.

## Controlled product builds

Build worker APIs are exposed under `/factory/build`. A build requires a completed approved repository execution, then passes through deterministic planning, dry-run validation, a separate approval, execution, security review, and optional rollback.

See [docs/build_workers.md](docs/build_workers.md) for worker governance and [docs/renovation_os_product_logic.md](docs/renovation_os_product_logic.md) for the implemented product behavior.

## Vertical Solutions

RenovationOS Operations Foundation is the first production vertical. It turns persisted project scope, room dimensions, quantities, and local rates into reproducible estimates and proposals, carries accepted work through job documentation and change-order approval, and coordinates dependency schedules, crews, and material deliveries.

## Marketplace

The vertical catalog includes **RenovationOS Operations Foundation** under Construction and Operations. Version 3 adds project scheduling, crew coordination, delivery tracking, schedule conflict detection, and delay impact analysis to the existing estimate, proposal, documentation, and change-order capabilities.

## API Reference

Renovation APIs are available under `/renovation` for estimate creation/read and proposal creation/read/export. RBAC scopes are `renovation.estimate.read`, `renovation.estimate.write`, `renovation.proposal.read`, and `renovation.proposal.write`.

See [docs/renovationos_foundation.md](docs/renovationos_foundation.md) for architecture, models, templates, replay behavior, and example requests.

Operations APIs add jobs, daily logs, field notes, change-order creation/read/approval/rejection/export, and complete job history. See [docs/renovationos_operations.md](docs/renovationos_operations.md).

Scheduling APIs add schedules, recalculation, crews, availability, assignments, material deliveries, and customer-facing job schedule summaries. See [docs/renovationos_scheduling.md](docs/renovationos_scheduling.md).
