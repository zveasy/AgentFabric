"""Initial Generation 4 document collections."""

from __future__ import annotations

from agentfabric.persistence import PersistenceStore


COLLECTIONS = [
    "agents",
    "identities",
    "certificates",
    "capabilities",
    "mesh_messages",
    "conversations",
    "workflows",
    "task_graphs",
    "checkpoints",
    "shared_context",
    "events",
    "reputation",
    "runtime_memory",
    "organizations",
    "tenants",
    "teams",
    "memberships",
    "usage_events",
    "quota_policies",
    "billing_plans",
    "audit_exports",
    "marketplace_packages",
    "marketplace_entitlements",
    "marketplace_reviews",
    "marketplace_installs",
    "governance_orgs",
    "governance_teams",
    "governance_charters",
    "governance_proposals",
    "governance_votes",
    "governance_approvals",
    "governance_decision_records",
    "governance_policies",
    "runtime_jobs",
    "runtime_dead_letters",
    "runtime_workers",
    "runtime_schedules",
    "federation_orgs",
    "federation_agreements",
    "federation_policies",
    "federation_remote_capabilities",
    "federation_messages",
    "federation_receipts",
    "federation_nonces",
    "federation_delegations",
]


def apply(store: PersistenceStore) -> None:
    store.initialize()
    for collection in COLLECTIONS:
        store.put("_collections", collection, {"name": collection})


def validate(store: PersistenceStore) -> None:
    existing = set(store.keys("_collections"))
    missing = [collection for collection in COLLECTIONS if collection not in existing]
    if missing:
        raise RuntimeError(f"missing collections: {', '.join(missing)}")
