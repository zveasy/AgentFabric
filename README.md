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
- `agentfabric/verticals/renovation/finance`, `profitability`, `invoicing`: actual job costs, margin variance, cost overruns, receivables, payables, cash-flow forecasts, and owner summaries.
- `agentfabric/verticals/renovation/leads`, `crm`, `communications`, `customer_portal`: lead acquisition, opportunities, follow-ups, appointments, communication history, and customer-safe project views.
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

Run the RenovationOS MVP locally:

`AGENTFABRIC_BOOTSTRAP_TOKEN=bootstrap-dev AGENTFABRIC_JWT_SECRET=change-me-for-local-dev-only python -m agentfabric.cli api-run --database-url "sqlite:///./agentfabric_api.db" --redis-url "memory://" --host 127.0.0.1 --port 8000`

Required local environment:

- `AGENTFABRIC_BOOTSTRAP_TOKEN`: bootstrap token used to create the first principal.
- `AGENTFABRIC_JWT_SECRET`: local JWT signing secret. In production it must be non-default and at least 32 characters.
- `AGENTFABRIC_STATE_STORE_BACKEND`: optional; defaults to `sqlite`. Set to `memory` only for throwaway runs.
- `AGENTFABRIC_STATE_STORE_PATH`: optional; chooses the SQLite document-store file. If unset with a SQLite API database, AgentFabric uses a sibling `*.state.db` file.

Then open `http://127.0.0.1:8000/renovation/app` or `http://127.0.0.1:3000/renovation/app` if you run the API on port 3000. The browser console is now a small RenovationOS operator cockpit: dashboard metrics, lead intake, customer list, estimate builder, proposal view, job board, schedule view, cost/profitability, invoice/payment, customer portal preview, and the durable MVP runs/replay/resume panel.

RenovationOS cockpit records are persisted in the configured state store. With the default SQLite state-store backend, the API uses `AGENTFABRIC_STATE_STORE_PATH` when set, or a sibling `*.state.db` file next to the SQLite API database. Set `AGENTFABRIC_STATE_STORE_BACKEND=memory` only for throwaway demos because operator records and MVP runs will not survive process restart.

Cockpit RBAC:

- `viewer`: read-only access to cockpit records, metrics, portal views, and MVP run history.
- `operator`: create and update RenovationOS workflow records.
- `owner`: manage workflow records and assign RenovationOS cockpit account roles.

## RenovationOS SaaS readiness

The cockpit now includes a local SaaS foundation while keeping the single-machine demo workflow intact:

- Account context and role assignment endpoints for owner/operator/viewer access.
- Proposal PDF export from persisted proposal and estimate data.
- Local file attachments for customers, leads, estimates, proposals, jobs, invoices, and payments.
- Provider-agnostic local stubs for notifications, calendar sync, and invoice payment links/status.
- Dashboard metrics remain tenant-scoped and are safe for viewer access.

New local environment:

- `AGENTFABRIC_RENOVATION_STORAGE_DIR`: directory for uploaded RenovationOS files. Defaults to `/tmp/agentfabric-renovation-storage`.
- `AGENTFABRIC_RENOVATION_MAX_UPLOAD_BYTES`: maximum accepted attachment size. Defaults to `10000000`.
- `AGENTFABRIC_STATE_STORE_PATH`: SQLite state-store file for durable cockpit records.
- `AGENTFABRIC_DATABASE_URL`: API database URL. For local SQLite production-style runs, mount the database directory as a volume.

Example production-style local command:

`AGENTFABRIC_ENVIRONMENT=production AGENTFABRIC_BOOTSTRAP_TOKEN=bootstrap-dev AGENTFABRIC_JWT_SECRET=replace-with-at-least-32-characters AGENTFABRIC_STATE_STORE_PATH=/data/agentfabric.state.db AGENTFABRIC_RENOVATION_STORAGE_DIR=/data/renovation-files python -m agentfabric.cli api-run --database-url "sqlite:////data/agentfabric_api.db" --redis-url "memory://" --host 0.0.0.0 --port 8000`

Container notes:

- The Docker image exposes port `8000`.
- Mount `/data` for SQLite databases, state-store durability, queue files when used, and RenovationOS attachments.
- The image health check calls `/health`.
- Local notification, calendar, and payment providers are deterministic stubs. Replace them with SendGrid/Twilio, Google/Outlook calendar, and Stripe/Adyen-style providers before production customer use.
- Attachment download/archive, provider validation, payment webhook status records, and branded proposal/invoice PDFs are available through the RenovationOS API while remaining deterministic locally.

RenovationOS integration settings:

- `AGENTFABRIC_RENOVATION_EMAIL_PROVIDER`: `local` or `smtp`. Defaults to `local`.
- `AGENTFABRIC_RENOVATION_SMTP_HOST`, `AGENTFABRIC_RENOVATION_SMTP_PORT`, `AGENTFABRIC_RENOVATION_SMTP_USERNAME`, `AGENTFABRIC_RENOVATION_SMTP_PASSWORD`: SMTP connection settings.
- `AGENTFABRIC_RENOVATION_EMAIL_SENDER`, `AGENTFABRIC_RENOVATION_EMAIL_REPLY_TO`: default sender identity.
- `AGENTFABRIC_RENOVATION_SMTP_LIVE_ENABLED`: set `true` only after credentials, SPF/DKIM, and test sends are verified. When false, SMTP payloads are validated and recorded without live delivery.
- `AGENTFABRIC_RENOVATION_SMS_PROVIDER`: `local` or `twilio`. The Twilio-compatible adapter expects a sender plus account credentials.
- `AGENTFABRIC_RENOVATION_SMS_SENDER_ID`, `AGENTFABRIC_RENOVATION_SMS_ACCOUNT_SID`, `AGENTFABRIC_RENOVATION_SMS_AUTH_TOKEN`: SMS sender and provider credentials.
- `AGENTFABRIC_RENOVATION_CALENDAR_PROVIDER`: `local`, `google`, or `outlook`. Google/Outlook modes are OAuth-ready shells until live OAuth is connected.
- `AGENTFABRIC_RENOVATION_CALENDAR_OAUTH_CLIENT_ID`, `AGENTFABRIC_RENOVATION_CALENDAR_OAUTH_CLIENT_SECRET`: reserved for calendar OAuth setup.
- `AGENTFABRIC_RENOVATION_PAYMENT_PROVIDER`: `local` or `stripe`. Stripe mode uses deterministic local links until live payment keys are wired.
- `AGENTFABRIC_RENOVATION_PAYMENT_SECRET_KEY`, `AGENTFABRIC_RENOVATION_PAYMENT_WEBHOOK_SECRET`: reserved for Stripe-compatible payment links and webhook signature verification.

Local/stub mode is the default for email, SMS, calendar, and payments so demos and tests do not need network access or real credentials. Live mode should be enabled only in a controlled environment with secrets stored outside source control. Webhook handlers must reject invalid signatures before payment state changes are trusted.

SaaS API examples:

`curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/renovation/account`

`curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"account_id":"operator-a","role":"operator"}' http://127.0.0.1:8000/renovation/accounts/roles`

`curl -H "Authorization: Bearer $TOKEN" -o proposal.pdf http://127.0.0.1:8000/renovation/proposals/$PROPOSAL_ID/pdf`

`curl -X POST -H "Authorization: Bearer $TOKEN" -F "file=@scope.pdf" http://127.0.0.1:8000/renovation/files/proposal/$PROPOSAL_ID`

`curl -H "Authorization: Bearer $TOKEN" -o invoice.pdf http://127.0.0.1:8000/renovation/invoices/$INVOICE_ID/pdf`

`curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"status":"paid","provider_reference_id":"pay-ref-1","idempotency_key":"webhook-1","invoice_id":"'$INVOICE_ID'"}' http://127.0.0.1:8000/renovation/payments/webhook`
- `owner`: all operator actions plus tenant/auth administration.

Core cockpit APIs:

- `GET /renovation/metrics`
- `POST|GET /renovation/customers`
- `GET /renovation/customers/{customer_id}`
- `POST|GET /renovation/leads`
- `GET /renovation/leads/{lead_id}`
- `POST /renovation/leads/{lead_id}/convert`
- `POST|GET /renovation/estimates`
- `GET /renovation/estimates/{estimate_id}`
- `POST /renovation/estimates/{estimate_id}/approve`
- `POST|GET /renovation/proposals`
- `GET /renovation/proposals/{proposal_id}`
- `POST /renovation/proposals/{proposal_id}/accept`
- `POST|GET /renovation/jobs`
- `GET /renovation/jobs/{job_id}`
- `PATCH /renovation/jobs/{job_id}/status`
- `POST|GET /renovation/jobs/{job_id}/schedule`
- `POST|GET /renovation/jobs/{job_id}/costs`
- `GET /renovation/jobs/{job_id}/profitability`
- `POST|GET /renovation/jobs/{job_id}/invoices`
- `POST /renovation/invoices/{invoice_id}/payments`
- `GET /renovation/jobs/{job_id}/portal`

Example cockpit calls:

`curl -sS -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"name":"Morgan Homeowner","email":"morgan@example.com","phone":"555-0140","address":"200 Oak Street"}' http://127.0.0.1:8000/renovation/customers`

`curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/renovation/metrics`

`curl -sS -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"status":"planned"}' http://127.0.0.1:8000/renovation/jobs/$JOB_ID/status`

Known cockpit limitations:

- Proposal/job creation still relies on the deterministic RenovationOS estimate and proposal templates already in the repo.
- Customer portal previews require enough job context to build a customer-safe status view.
- The embedded dashboard is intentionally lightweight HTML/JS for local demos, not a production frontend shell.

The MVP API surface is:

- `POST /renovation/mvp/demo`: compatibility alias for creating a default MVP run.
- `POST /renovation/mvp/runs`: create an idempotent run. Include `{"idempotency_key": "demo-001"}` to avoid duplicate records.
- `GET /renovation/mvp/runs`: list tenant runs.
- `GET /renovation/mvp/runs/{run_id}`: inspect run status, steps, entity IDs, financial summary, and failure details.
- `POST /renovation/mvp/runs/{run_id}/replay`: record a replay of persisted run output.
- `POST /renovation/mvp/runs/{run_id}/resume`: continue a failed or incomplete run from the last incomplete step.
- `GET /renovation/mvp/runs/{run_id}/portal`: fetch customer-safe portal/status output.
- `GET /renovation/health`: check RenovationOS state-store health and run count.

Example MVP API call:

`curl -sS -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"idempotency_key":"demo-001","project":{"title":"Kitchen Remodel"},"customer":{"name":"Morgan Homeowner"}}' http://127.0.0.1:8000/renovation/mvp/runs`

Run tests:

`python -m pytest --collect-only`

`python -m pytest tests/test_renovation_api.py -q`

`python -m pytest`

`python -m unittest discover -s tests`

Troubleshooting:

- If imports appear to hang inside `importlib`, regenerate first-party bytecode caches with `python -m compileall -f -q agentfabric agent_connectors agent_observability veil_client runtime registry scheduler orchestration memory evaluations versioning marketplace connectors tests`.
- If SQLite state cannot be created, check write permissions for the API database directory or set `AGENTFABRIC_STATE_STORE_PATH` to a writable path.
- If the dashboard returns `401`, create/issue a principal token first and paste it into the Bearer token field.
- Current local limitation: full test collection can still be slow on macOS/Python 3.13 because the suite imports the entire API stack and assertion rewriting touches many modules.

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

RenovationOS Operations Foundation is the first production vertical. It covers lead intake through customer conversion, deterministic estimating and proposals, active project operations, schedules and crews, job profitability, communications, and customer-safe portal views.

## Marketplace

The vertical catalog includes **RenovationOS Operations Foundation** under Construction and Operations. Version 5 adds CRM, lead intake, follow-up workflows, customer communications, and portal views to the existing operational and financial capabilities.

## API Reference

Renovation APIs are available under `/renovation` for estimate creation/read and proposal creation/read/export. RBAC scopes are `renovation.estimate.read`, `renovation.estimate.write`, `renovation.proposal.read`, and `renovation.proposal.write`.

See [docs/renovationos_foundation.md](docs/renovationos_foundation.md) for architecture, models, templates, replay behavior, and example requests.

Operations APIs add jobs, daily logs, field notes, change-order creation/read/approval/rejection/export, and complete job history. See [docs/renovationos_operations.md](docs/renovationos_operations.md).

Scheduling APIs add schedules, recalculation, crews, availability, assignments, material deliveries, and customer-facing job schedule summaries. See [docs/renovationos_scheduling.md](docs/renovationos_scheduling.md).

Finance APIs add job costs, profitability scorecards, invoices, payments, vendor payables, fixed-window cash-flow forecasts, and owner summaries. See [docs/renovationos_finance.md](docs/renovationos_finance.md).

CRM and portal APIs add leads, opportunity stages, follow-ups, appointments, site visits, customer messages, portal views, and customer-status summaries. See [docs/renovationos_crm_portal.md](docs/renovationos_crm_portal.md).
