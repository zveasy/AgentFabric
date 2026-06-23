"""Renovation API route contract metadata."""

ROUTES = {
    "estimate_create": ("POST", "/renovation/estimate", "renovation.estimate.write"),
    "proposal_create": ("POST", "/renovation/proposal", "renovation.proposal.write"),
    "estimate_get": ("GET", "/renovation/estimate/{estimate_id}", "renovation.estimate.read"),
    "proposal_get": ("GET", "/renovation/proposal/{proposal_id}", "renovation.proposal.read"),
    "proposal_export": ("POST", "/renovation/proposal/export", "renovation.proposal.write"),
    "job_create": ("POST", "/renovation/jobs", "renovation.jobs.write"),
    "job_get": ("GET", "/renovation/jobs/{job_id}", "renovation.jobs.read"),
    "daily_log_create": (
        "POST",
        "/renovation/jobs/{job_id}/daily-log",
        "renovation.documentation.write",
    ),
    "field_note_create": (
        "POST",
        "/renovation/jobs/{job_id}/field-note",
        "renovation.documentation.write",
    ),
    "change_order_create": (
        "POST",
        "/renovation/change-orders",
        "renovation.change_orders.write",
    ),
    "change_order_get": (
        "GET",
        "/renovation/change-orders/{change_order_id}",
        "renovation.change_orders.read",
    ),
    "change_order_approve": (
        "POST",
        "/renovation/change-orders/{change_order_id}/approve",
        "renovation.change_orders.approve",
    ),
    "change_order_reject": (
        "POST",
        "/renovation/change-orders/{change_order_id}/reject",
        "renovation.change_orders.approve",
    ),
    "change_order_export": (
        "POST",
        "/renovation/change-orders/{change_order_id}/export",
        "renovation.change_orders.write",
    ),
    "schedule_create": (
        "POST",
        "/renovation/schedules",
        "renovation.scheduling.write",
    ),
    "schedule_get": (
        "GET",
        "/renovation/schedules/{schedule_id}",
        "renovation.scheduling.read",
    ),
    "schedule_recalculate": (
        "POST",
        "/renovation/schedules/{schedule_id}/recalculate",
        "renovation.scheduling.write",
    ),
    "crew_create": ("POST", "/renovation/crews", "renovation.crews.write"),
    "crew_get": (
        "GET",
        "/renovation/crews/{crew_id}",
        "renovation.crews.read",
    ),
    "crew_availability": (
        "POST",
        "/renovation/crews/{crew_id}/availability",
        "renovation.crews.write",
    ),
    "crew_assignment": (
        "POST",
        "/renovation/crew-assignments",
        "renovation.crews.write",
    ),
    "material_delivery": (
        "POST",
        "/renovation/material-deliveries",
        "renovation.deliveries.write",
    ),
    "schedule_summary": (
        "GET",
        "/renovation/jobs/{job_id}/schedule-summary",
        "renovation.scheduling.read",
    ),
}
