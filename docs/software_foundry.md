# AI Software Foundry

AgentFabric now includes deterministic infrastructure for generating, evaluating, packaging, and operating repositories and industry platforms.

## Architecture

The foundry is split into explicit layers:

* `repository_factory`: canonical manifests, templates, package structures, dependency graphs, and scaffolding.
* `blueprints`: industry-specific APIs, events, persistence, RBAC, quality, observability, and deployment models.
* `domain_knowledge`: versioned terminology, entities, workflows, metrics, APIs, and compliance references.
* `domain_platforms`: platform capabilities, package graphs, deployment targets, and required evidence.
* `software_factory`: signed generation artifacts from requirements through release validation.
* `repository_lifecycle`: create, update, deprecate, archive, restore, clone, and fork operations.
* `repository_graph`: lineage, dependency, impact, and dependency-drift analysis.
* `software_teams`: auditable work assignments for architecture, backend, frontend, security, testing, documentation, and deployment teams.

All tenant data uses the shared persistence interfaces and durable hash-chained event store.

## Determinism

Repository manifests use canonical JSON with sorted collections. Repository and blueprint IDs are content-addressed. Stage artifact signatures are SHA-256 digests over canonical stage inputs, outputs, repository identity, and signer identity.

Lifecycle timestamps are operational metadata and are not part of deterministic manifest identity.

## Generation Flow

1. Idea
2. Requirements
3. Architecture
4. Repository blueprint
5. API, database, backend, and frontend generation
6. Tests
7. Documentation
8. Security review
9. Deployment
10. Release validation
11. Repository package

Each stage emits `factory.artifact.generated`. Validated packages emit `factory.repository.packaged`.

## Quality Gates

Repository generation requires evidence for:

* architecture quality
* code quality
* test coverage
* documentation completeness
* dependency health
* observability readiness
* security posture

Missing evidence or a failed threshold blocks repository creation and emits `factory.quality.failed`.

## Domain Platforms

The built-in catalog includes RenovationOS, TreasuryOS, TrustOS, EnergyOS, ManufacturingOS, DefenseOS, and SpaceOS.

RenovationOS seed definitions are stored in `platforms/renovation_os/` and cover estimation, change orders, contractor operations, materials, field photos, finance, homeowner workflows, trust evidence, and AgentFabric orchestration.

## APIs

* `POST /factory/ideas`
* `POST /factory/repositories`
* `POST /factory/platforms`
* `GET /factory/platforms`
* `GET /factory/repositories`
* `GET /factory/repositories/{id}`
* `GET /factory/lineage`
* `GET /factory/dependencies`
* `GET /factory/quality`

The API requires tenant context and the `factory:read`, `factory:write`, `factory:execute`, `factory:admin`, or `factory:quality` scopes as appropriate.

## Marketplace

Industry package metadata supports construction, treasury, trust, energy, manufacturing, and aerospace categories, package bundle IDs, compatibility matrices, and quality scores. Marketplace scanning fails closed for unsupported categories or quality scores below the release threshold.

## Audit

Audit bundles include ideas, repositories, platforms, signed artifacts, repository packages, quality scores, software-team tasks, lifecycle events, and release events.
