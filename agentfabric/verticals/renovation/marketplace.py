"""RenovationOS Foundation marketplace metadata."""

RENOVATION_FOUNDATION_PACKAGE = {
    "package_id": "renovationos-foundation",
    "name": "RenovationOS Operations Foundation",
    "version": "3.0.0",
    "category": "Construction",
    "secondary_category": "Operations",
    "private": True,
    "capabilities": [
        "estimate_generation",
        "proposal_generation",
        "job_documentation",
        "change_order_management",
        "project_history",
        "project_scheduling",
        "crew_coordination",
        "material_delivery_tracking",
        "delay_impact_analysis",
    ],
    "execution": "offline_deterministic",
    "tenant_isolation": True,
    "replay_support": True,
    "description": (
        "Deterministic renovation estimating, proposals, job documentation, "
        "change orders, scheduling, crews, and delivery coordination."
    ),
}
