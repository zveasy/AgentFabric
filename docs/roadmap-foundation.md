# Roadmap Foundation

This document captures the repository shape introduced for the roadmap's Phase 0.

## Principles

- AgentFabric must remain a standalone system.
- VEIL integration is API-only and isolated to `veil_client/`.
- Runtime, registry, memory, scheduling, and marketplace concerns are split into explicit packages instead of being implied by phase folders.
- The new foundation is additive for now so the existing `agentfabric/` implementation can continue to pass its current test surface while later phases migrate onto the new structure.

## Top-level packages

- `runtime`: agent specs, execution policies, and safe runtime contracts.
- `registry`: registration metadata, ownership, permission, and lifecycle records.
- `scheduler`: one-time and recurring task scheduling contracts.
- `orchestration`: workflow DAGs, approvals, retries, and execution state.
- `memory`: tenant-scoped and sanitized memory record shapes.
- `evaluations`: scorecards, thresholds, and publish readiness.
- `versioning`: version lineage, forks, merges, and rollback proposals.
- `marketplace`: listings, installation metadata, and visibility controls.
- `connectors`: external tool and service connector base protocols.
- `veil_client`: typed request and response models plus client interfaces for VEIL APIs.

## Next phases

- Phase 1 should place concrete VEIL client implementations behind `veil_client.interfaces.VeilClient`.
- Phase 2 should build `runtime` around the new `AgentSpec` and `ExecutionPolicy` contracts instead of the legacy phase modules.
- Phase 3 onward should move persistence and orchestration logic package by package while preserving fail-closed behavior.
