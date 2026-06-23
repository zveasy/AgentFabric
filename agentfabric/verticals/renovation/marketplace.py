"""RenovationOS Foundation marketplace metadata."""

RENOVATION_FOUNDATION_PACKAGE = {
    "package_id": "renovationos-foundation",
    "name": "RenovationOS Operations Foundation",
    "version": "2.0.0",
    "category": "Construction",
    "secondary_category": "Operations",
    "private": True,
    "capabilities": [
        "estimate_generation",
        "proposal_generation",
        "job_documentation",
        "change_order_management",
        "project_history",
    ],
    "execution": "offline_deterministic",
    "tenant_isolation": True,
    "replay_support": True,
    "description": "Deterministic renovation estimating, proposals, job documentation, and change orders.",
}
