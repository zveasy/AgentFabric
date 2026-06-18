# Pilot Readiness Matrix

## Completed Capabilities

- Tenant, team, membership, RBAC, quota, metering, and billing controls.
- Durable persistence, migrations, hash-chained events, memory, replay recovery.
- Signed marketplace publishing, scans, entitlement checks, reviews, reputation.
- Governance organizations, proposals, consensus, human approval, decision records.
- Cloud runtime jobs, workers, queues, schedules, health, and metrics.
- Federation orgs, trust agreements, signed messages, delegation, revocation, reputation.

## Remaining Risks

- VEIL and Aegis Gate are external dependencies and must be validated in pilot deployment.
- Runtime isolation depends on container/orchestrator sandbox posture.
- Federation transport adapter is local/mock in this repo and needs production transport.
- External vulnerability intelligence and SIEM forwarding are not fully automated.

## Pilot Assumptions

- One controlled enterprise tenant or a small set of explicitly federated tenants.
- Strict signing and production safety validation enabled.
- Operators can revoke federation agreements and packages quickly.
- VEIL provides policy, sanitization, token references, and audit authority.
- Aegis Gate controls restore authorization and policy authority.

## Dependencies

- PostgreSQL or approved durable DB.
- Redis or approved durable queue backend.
- VEIL API endpoint and credentials.
- Aegis Gate restore/policy endpoint.
- Secret manager for JWT, signing, registry, VEIL, and Aegis credentials.

## Staffing And Monitoring

- On-call engineer for API/runtime.
- Security owner for marketplace/federation incidents.
- Tenant admin contact for access and governance approvals.
- Dashboards for jobs, queues, workers, events, federation failures, and VEIL latency.

## Go/No-Go Checklist

- `python scripts/release_validate.py` passes.
- Production safety config passes.
- Threat model reviewed by security.
- Runbooks reviewed by operations.
- VEIL/Aegis connectivity tested.
- Federation agreements reviewed and revocation tested.
- Backup, restore, and event integrity procedures rehearsed.
