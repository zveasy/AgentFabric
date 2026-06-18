# AgentFabric Security Threat Model

## Scope

This model covers AgentFabric through Generation 10: runtime execution, marketplace supply chain, tenants, durable memory, governance, cloud workers, queues, federation, VEIL trust boundaries, Aegis restore authority, and audit/event integrity.

## Threats, Mitigations, Residual Risk, Tests

| Area | Threats | Mitigations | Residual Risk | Test Coverage |
| --- | --- | --- | --- | --- |
| Runtime agent execution | Untrusted agent payloads, tool abuse, sandbox escape, quota bypass | RBAC, tenant context, quota checks, runtime job allowlist, VEIL policy checks, no raw sensitive payload keys | Runtime sandbox depth depends on deployment isolation | `test_phase1_runtime.py`, `test_generation8_cloud_runtime.py` |
| Marketplace supply chain | Unsigned packages, unsafe permissions, dependency confusion, revoked packages | Signature verifier, trusted publishers, dependency resolver, scanner, entitlement checks, production strict signing | External vulnerability feeds are not integrated | `test_generation6_marketplace.py` |
| Tenant isolation | Cross-tenant reads/writes, tenantless API calls | TenantContext, tenant-filtered persistence, RBAC scopes, structured 401/403 errors | Global admin scope must be tightly issued | `test_generation5_enterprise.py`, `test_generation10_release.py` |
| Memory persistence | Raw sensitive values stored outside VEIL, cross-tenant memory leakage | Memory classifier, raw key rejection, VEIL token refs, tenant-scoped APIs | Semantic sensitive-data detection remains VEIL-owned | `test_generation4_durable.py` |
| Federation | Expired/revoked trust use, replayed messages, unsigned messages, raw payload exfiltration | TrustAgreement lifecycle, signatures, nonce replay protection, TTL, revocation events, VEIL policy checks | Real remote transport security is adapter-dependent | `test_generation9_federation.py` |
| Governance bypass | High-risk action execution before approval | Proposal status checks, consensus modes, human approval bridge, runtime governance check | Policy configuration mistakes can over-authorize roles | `test_generation7_governance.py` |
| Queue and workers | Dropped jobs, duplicate retries, tenant leakage, stale workers | Durable queue abstractions, dead-letter queue, tenant-scoped job APIs, heartbeat tracking | Distributed exactly-once execution is not guaranteed | `test_generation8_cloud_runtime.py` |
| VEIL boundary | AgentFabric implementing trust decisions internally | All trust checks call `veil_client`, no direct VEIL internals | Mock VEIL behavior is permissive in local tests | `test_repo_foundation.py`, generation boundary tests |
| Aegis restore boundary | Unauthorized raw restore or policy bypass | AgentFabric stores VEIL references only; restore authority remains outside AgentFabric | Aegis integration is an external dependency | `test_generation4_durable.py` |
| Audit/evidence integrity | Event tampering, missing audit records | Hash-chained event store, registered event types, replay validation, audit exports | Memory store is not tamper-resistant by itself | `test_generation4_durable.py`, `test_generation10_release.py` |

## Pilot Security Posture

AgentFabric is ready for controlled enterprise pilots when deployed with production safety validation enabled, strict package signing, Redis or SQLite-backed queues, non-default JWT secrets, VEIL connectivity, and operational review of federation agreements.
