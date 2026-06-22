# Build Workers

Generation 19 adds controlled build workers on top of approved Generation 18 repository executions.

## Build lifecycle

1. `POST /factory/build/plan` validates a completed repository execution and selects registered workers by capability, repository type, and domain.
2. `POST /factory/build/dry-run` regenerates all worker output and verifies the build ID and artifact hashes.
3. `POST /factory/build/approve` records the tenant, approver, timestamp, and exact plan digest.
4. `POST /factory/build/run` applies the approved product delta and records original contents for rollback.
5. `POST /factory/build/review` verifies completed security evidence and records the review decision.
6. `POST /factory/build/rollback` restores overwritten scaffold files and removes files introduced by the build.

Build reads, events, and artifacts are available under `/factory/build/{build_id}`. Registered workers are available at `/factory/build/workers`.

## Worker catalog

- Domain model worker
- Service logic worker
- API route worker
- Test worker
- Documentation worker
- Quality worker
- Security review worker

Each worker declares capabilities, supported repository types and domains, approval requirements, and quality gates. Missing workers, unsupported inputs, incomplete execution artifacts, and failed security evidence block the build.

## Determinism and isolation

Workers use approved manifests and local templates only. They do not invoke open-ended code generation or external pricing/data services. Build IDs are content-derived, runtime output remains tenant-namespaced, and replay must reproduce the original output hashes.

Audit bundles include build plans, worker IDs, input/output hashes, approvals, reviews, quality gates, artifacts, and rollback outcomes. Generated source content is excluded from audit exports.
