# AgentFabric

Production-ready runtime and marketplace control plane for AI agents.

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
- **Phase 5 (AgentForge Projects)**: depth-first agent projects with maintainers, contribution zones, automated evaluation gates, merge governance, and release channels.

## Production hardening (P0/P1/P2)

- **P0**: durable persistence layer, auth/token lifecycle, migration-driven schema management, and service endpoints.
- **P1**: package security pipeline, stronger sandbox policies, metrics/traces, backup/restore, and retry worker support.
- **P2**: moderation queue + resolution, billing settlement pathways, GDPR flows, SIEM export, and legal document lifecycle.

## AgentForge depth-first model

AgentFabric now supports **Agent Projects**: maintained, versioned intelligence assets rather than disposable one-off agents.

Each project includes:

- Canonical `main` branch and contributor branches.
- Maintainers and merge governance.
- Contribution manifests with measurable improvement data.
- Automated evaluation gates for quality/regression checks.
- Release channels: `stable`, `beta`, `nightly`, `enterprise-certified`.
- Browser interface at `/forge` for interactive project operations.

Meaningful merges are enforced by policy: contributions must show measurable upside (for example accuracy/reliability/domain coverage) without unacceptable latency/cost/safety regressions.

## Repository layout

- `agentfabric/phase1`, `agentfabric/phase2`, `agentfabric/phase3`, `agentfabric/phase4`: phase implementations.
- `agentfabric/production`: control-plane services and durable operations modules.
- `agentfabric/server`: FastAPI app, auth, queue, DB/session, worker, and integrations.
- `agentfabric/cli.py`: production-oriented CLI entrypoint.
- `agents/manifest_schema/manifest.v1.schema.json`: manifest schema.
- `tests`: runtime + production + API stack tests.

## Quickstart

Run tests:

`python -m unittest discover -s tests -v`

Run migrations:

`python -m agentfabric.cli db-migrate --database-url "postgresql+psycopg://agentfabric:agentfabric@localhost:5432/agentfabric"`

Run API:

`python -m agentfabric.cli api-run --database-url "postgresql+psycopg://agentfabric:agentfabric@localhost:5432/agentfabric" --redis-url "redis://localhost:6379/0" --jwt-secret "change-me" --host 0.0.0.0 --port 8000`

Run worker:

`python -m agentfabric.cli worker-run --database-url "postgresql+psycopg://agentfabric:agentfabric@localhost:5432/agentfabric" --redis-url "redis://localhost:6379/0" --queue-name default`

## Deployment artifacts

- GitHub Actions: `.github/workflows/ci.yml`, `.github/workflows/cd.yml`
- Container: `Dockerfile`, `docker-compose.yml`
- Kubernetes: `deploy/k8s/*`
