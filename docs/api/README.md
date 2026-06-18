# AgentFabric API Contracts

All protected endpoints require `Authorization: Bearer <JWT>`. Tenant-scoped endpoints derive tenant context from the JWT unless a path parameter explicitly names a tenant. Failures use:

```json
{"error":{"code":"rbac_or_tenant_denial","message":"insufficient scope","status":403}}
```

OpenAPI export:

```bash
python scripts/export_openapi.py
```

## Tenant APIs

| Method | Path | Scope | Body | Response | Failure Modes | Audit/Event |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/tenants` | `tenant.manage` | tenant id/name/plan | tenant record | 401,403,409 | `tenant.created` |
| GET | `/tenants` | `tenant.manage` | none | list | 401,403 | none |
| GET | `/tenants/{tenant_id}` | `tenant.manage` | none | tenant | 401,403,404 | none |
| POST/GET | `/tenants/{tenant_id}/teams` | `team.manage` | team | team/list | 401,403,404 | `team.created` |
| POST/GET | `/tenants/{tenant_id}/members` | `members.manage` | member | member/list | 401,403,404 | `member.added` |
| GET/PATCH | `/tenants/{tenant_id}/quotas` | `quotas.read/manage` | quota patch | quota state | 401,403,409 | `quota.updated` |
| GET/PATCH | `/tenants/{tenant_id}/billing` | `billing.read/manage` | plan patch | plan | 401,403,409 | `billing.plan_updated` |

## Runtime APIs

| Method | Path | Scope | Body | Response | Failure Modes | Audit/Event |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/runtime/jobs` | `runtime.jobs.manage` | job type/payload | job | 400,401,403,409 | `runtime.job.created` |
| GET | `/runtime/jobs` | `runtime.jobs.read` | none | jobs | 401,403 | none |
| GET | `/runtime/jobs/{job_id}` | `runtime.jobs.read` | none | job | 401,403,404 | none |
| POST | `/runtime/jobs/{job_id}/cancel` | `runtime.jobs.manage` | none | job | 401,403,404 | `runtime.job.cancelled` |
| POST | `/runtime/jobs/{job_id}/retry` | `runtime.jobs.manage` | none | job | 401,403,404,409 | `runtime.job.retried` |
| GET/POST | `/runtime/dead-letter` | `runtime.jobs.read/manage` | requeue none | dead letters/job | 401,403,404 | `runtime.job.retried` |
| POST/GET | `/runtime/workers` | `runtime.workers.manage/read` | worker | worker/list | 401,403,404 | `runtime.worker.registered` |
| POST/GET | `/runtime/schedules` | `runtime.schedules.manage/read` | schedule | schedule/list | 401,403 | `runtime.schedule.created` |

## Mesh And Workflow APIs

| Method | Path | Scope | Body | Response | Failure Modes | Audit/Event |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/mesh/send` | `mesh.send` | message | sent message | 401,403,409 | `message` |
| POST | `/mesh/broadcast` | `mesh.broadcast` | message | sent messages | 401,403,409 | `message` |
| POST | `/workflow/start` | `workflow.start` | graph | workflow state | 401,403,409 | `workflow.started` |
| GET | `/workflow/{id}` | `workflow.read` | none | workflow | 401,403,404 | none |
| GET | `/workflow/{id}/events` | `events.read`, `workflow.read` | none | events | 401,403,404 | none |
| POST | `/workflow/{id}/recover` | `workflow.recover` | none | recovery | 401,403,409 | metered |

## Marketplace APIs

Marketplace endpoints under `/marketplace/*` require `marketplace.read`, `marketplace.publish`, `marketplace.install`, or `marketplace.review`. They enforce tenant context, signatures, scans, entitlements, quotas, and billing plan permissions. Events include package published, verified, rejected, installed, uninstalled, upgraded, rolled back, entitlement granted/revoked, review submitted, and abuse report submitted.

## Governance APIs

Governance endpoints under `/governance/*` require `governance.manage`, `governance.read`, `governance.propose`, `governance.vote`, `governance.execute`, or `governance.approve`. They cover orgs, teams, charters, proposals, votes, execution, decision records, and approval queues. Events cover proposal, vote, consensus, human approval, and governed action lifecycle.

## Federation APIs

Federation endpoints under `/federation/*` require `federation.manage`, `federation.read`, `federation.message`, or `federation.delegate`. They cover federated orgs, trust agreements, capability import/publish/discovery, signed messages, receipts, delegations, and federated reputation. Failures include expired/revoked agreement, bad signature, replay, TTL, VEIL denial, raw payload rejection, quota, and tenant isolation denial.

## Memory, Events, Health, Metrics

Memory endpoints require `memory.read/write/delete` and persist VEIL references only. Event endpoints require `events.read` and are tenant-filtered. Health endpoints cover `/health`, `/health/persistence`, `/health/runtime`, `/health/workers`, `/health/queues`; metrics include Prometheus `/metrics` and tenant usage `/metrics/tenants/{tenant_id}`.
