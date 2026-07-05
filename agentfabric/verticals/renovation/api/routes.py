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
    "job_cost_create": (
        "POST",
        "/renovation/jobs/{job_id}/costs",
        "renovation.finance.write",
    ),
    "job_profitability": (
        "GET",
        "/renovation/jobs/{job_id}/profitability",
        "renovation.profitability.read",
    ),
    "invoice_create": (
        "POST",
        "/renovation/invoices",
        "renovation.invoicing.write",
    ),
    "invoice_payment": (
        "POST",
        "/renovation/invoices/{invoice_id}/payment",
        "renovation.invoicing.write",
    ),
    "invoice_get": (
        "GET",
        "/renovation/invoices/{invoice_id}",
        "renovation.invoicing.read",
    ),
    "payable_create": (
        "POST",
        "/renovation/payables",
        "renovation.invoicing.write",
    ),
    "payable_payment": (
        "POST",
        "/renovation/payables/{payable_id}/payment",
        "renovation.invoicing.write",
    ),
    "cash_flow_forecast": (
        "GET",
        "/renovation/cash-flow/forecast",
        "renovation.cashflow.read",
    ),
    "owner_summary": (
        "GET",
        "/renovation/owner-summary",
        "renovation.finance.read",
    ),
    "lead_create": ("POST", "/renovation/leads", "renovation.leads.write"),
    "lead_get": (
        "GET",
        "/renovation/leads/{lead_id}",
        "renovation.leads.read",
    ),
    "lead_status": (
        "POST",
        "/renovation/leads/{lead_id}/status",
        "renovation.leads.write",
    ),
    "lead_convert": (
        "POST",
        "/renovation/leads/{lead_id}/convert",
        "renovation.leads.write",
    ),
    "opportunity_create": (
        "POST",
        "/renovation/opportunities",
        "renovation.crm.write",
    ),
    "opportunity_get": (
        "GET",
        "/renovation/opportunities/{opportunity_id}",
        "renovation.crm.read",
    ),
    "opportunity_stage": (
        "POST",
        "/renovation/opportunities/{opportunity_id}/stage",
        "renovation.crm.write",
    ),
    "follow_up_create": (
        "POST",
        "/renovation/follow-ups",
        "renovation.crm.write",
    ),
    "appointment_create": (
        "POST",
        "/renovation/appointments",
        "renovation.crm.write",
    ),
    "site_visit_create": (
        "POST",
        "/renovation/site-visits",
        "renovation.crm.write",
    ),
    "customer_message_create": (
        "POST",
        "/renovation/customer-messages",
        "renovation.communications.write",
    ),
    "customer_portal_view": (
        "GET",
        "/renovation/customers/{customer_id}/portal-view",
        "renovation.portal.read",
    ),
    "customer_job_status": (
        "GET",
        "/renovation/jobs/{job_id}/customer-status",
        "renovation.portal.read",
    ),
    "mvp_demo": ("POST", "/renovation/mvp/demo", "renovation.mvp.run"),
    "mvp_run_create": ("POST", "/renovation/mvp/runs", "renovation.mvp.run"),
    "mvp_runs_list": ("GET", "/renovation/mvp/runs", "renovation.mvp.read"),
    "mvp_run_get": ("GET", "/renovation/mvp/runs/{run_id}", "renovation.mvp.read"),
    "mvp_run_replay": (
        "POST",
        "/renovation/mvp/runs/{run_id}/replay",
        "renovation.mvp.run",
    ),
    "mvp_run_resume": (
        "POST",
        "/renovation/mvp/runs/{run_id}/resume",
        "renovation.mvp.run",
    ),
    "mvp_run_portal": (
        "GET",
        "/renovation/mvp/runs/{run_id}/portal",
        "renovation.mvp.read",
    ),
    "renovation_health": ("GET", "/renovation/health", "renovation.mvp.read"),
    "operator_metrics": ("GET", "/renovation/metrics", "renovation.operator.read"),
    "operator_customer_create": (
        "POST",
        "/renovation/customers",
        "renovation.operator.write",
    ),
    "operator_customer_list": (
        "GET",
        "/renovation/customers",
        "renovation.operator.read",
    ),
    "operator_customer_get": (
        "GET",
        "/renovation/customers/{customer_id}",
        "renovation.operator.read",
    ),
    "operator_leads_list": ("GET", "/renovation/leads", "renovation.operator.read"),
    "operator_estimate_create": (
        "POST",
        "/renovation/estimates",
        "renovation.operator.write",
    ),
    "operator_estimate_list": (
        "GET",
        "/renovation/estimates",
        "renovation.operator.read",
    ),
    "operator_estimate_get": (
        "GET",
        "/renovation/estimates/{estimate_id}",
        "renovation.operator.read",
    ),
    "operator_estimate_approve": (
        "POST",
        "/renovation/estimates/{estimate_id}/approve",
        "renovation.operator.write",
    ),
    "operator_proposal_create": (
        "POST",
        "/renovation/proposals",
        "renovation.operator.write",
    ),
    "operator_proposal_list": (
        "GET",
        "/renovation/proposals",
        "renovation.operator.read",
    ),
    "operator_proposal_get": (
        "GET",
        "/renovation/proposals/{proposal_id}",
        "renovation.operator.read",
    ),
    "operator_proposal_accept": (
        "POST",
        "/renovation/proposals/{proposal_id}/accept",
        "renovation.operator.write",
    ),
    "operator_job_list": ("GET", "/renovation/jobs", "renovation.operator.read"),
    "operator_job_status": (
        "PATCH",
        "/renovation/jobs/{job_id}/status",
        "renovation.operator.write",
    ),
    "operator_job_schedule_create": (
        "POST",
        "/renovation/jobs/{job_id}/schedule",
        "renovation.operator.write",
    ),
    "operator_job_schedule_list": (
        "GET",
        "/renovation/jobs/{job_id}/schedule",
        "renovation.operator.read",
    ),
    "operator_job_cost_list": (
        "GET",
        "/renovation/jobs/{job_id}/costs",
        "renovation.operator.read",
    ),
    "operator_job_invoice_create": (
        "POST",
        "/renovation/jobs/{job_id}/invoices",
        "renovation.operator.write",
    ),
    "operator_job_invoice_list": (
        "GET",
        "/renovation/jobs/{job_id}/invoices",
        "renovation.operator.read",
    ),
    "operator_invoice_payment": (
        "POST",
        "/renovation/invoices/{invoice_id}/payments",
        "renovation.operator.write",
    ),
    "operator_job_portal": (
        "GET",
        "/renovation/jobs/{job_id}/portal",
        "renovation.operator.read",
    ),
}
