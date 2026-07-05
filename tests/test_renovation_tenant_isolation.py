from __future__ import annotations

import unittest

from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError

from tests.renovation_helpers import (
    CHANGE_ORDER_PAYLOAD,
    CREW_PAYLOAD,
    ESTIMATE_PAYLOAD,
    PROPOSAL_PAYLOAD,
    INVOICE_PAYLOAD,
    LEAD_PAYLOAD,
    MATERIAL_COST_PAYLOAD,
    SCHEDULE_PAYLOAD,
    job_fixture,
    service_fixture,
)


class RenovationTenantIsolationTests(unittest.TestCase):
    def test_cross_tenant_estimate_proposal_and_export_are_denied(self) -> None:
        _, _, service, context = service_fixture()
        estimate = service.create_estimate(context, ESTIMATE_PAYLOAD)
        proposal = service.create_proposal(
            context,
            {**PROPOSAL_PAYLOAD, "estimate_id": estimate.estimate_id},
        )
        other = TenantContext("tenant-b", "org-b", "owner-b", ())
        with self.assertRaises(AuthorizationError):
            service.get_estimate(other, estimate.estimate_id)
        with self.assertRaises(AuthorizationError):
            service.get_proposal(other, proposal.proposal_id)
        with self.assertRaises(AuthorizationError):
            service.export_proposal(other, proposal.proposal_id)

    def test_marketplace_package_metadata(self) -> None:
        _, _, service, _ = service_fixture()
        package = service.marketplace_package()
        self.assertEqual(package["name"], "RenovationOS Operations Foundation")
        self.assertEqual(package["category"], "Construction")
        self.assertEqual(package["secondary_category"], "Operations")
        self.assertEqual(package["execution"], "offline_deterministic")
        self.assertTrue(package["tenant_isolation"])
        self.assertTrue(package["replay_support"])
        self.assertIn("job_documentation", package["capabilities"])
        self.assertIn("change_order_management", package["capabilities"])
        self.assertIn("project_scheduling", package["capabilities"])
        self.assertIn("crew_coordination", package["capabilities"])
        self.assertIn("job_profitability", package["capabilities"])
        self.assertIn("cash_flow_forecasting", package["capabilities"])
        self.assertIn("lead_intake", package["capabilities"])
        self.assertIn("customer_portal", package["capabilities"])

    def test_cross_tenant_job_history_and_change_order_are_denied(self) -> None:
        _, _, service, context, _, _, job = job_fixture()
        order = service.create_change_order(
            context,
            {**CHANGE_ORDER_PAYLOAD, "job_id": job.job_id},
        )
        other = TenantContext("tenant-b", "org-b", "owner-b", ())
        with self.assertRaises(AuthorizationError):
            service.get_job(other, job.job_id)
        with self.assertRaises(AuthorizationError):
            service.project_history(other, job.job_id)
        with self.assertRaises(AuthorizationError):
            service.get_change_order(other, order.change_order_id)
        with self.assertRaises(AuthorizationError):
            service.export_change_order(other, order.change_order_id)

    def test_cross_tenant_schedules_and_crews_are_denied(self) -> None:
        _, _, service, context, _, _, job = job_fixture()
        schedule = service.create_schedule(
            context,
            {**SCHEDULE_PAYLOAD, "job_id": job.job_id},
        )
        crew = service.create_crew(context, CREW_PAYLOAD)
        other = TenantContext("tenant-b", "org-b", "owner-b", ())
        with self.assertRaises(AuthorizationError):
            service.get_schedule(other, schedule.schedule_id)
        with self.assertRaises(AuthorizationError):
            service.get_crew(other, crew.crew_id)
        with self.assertRaises(AuthorizationError):
            service.create_crew_assignment(
                other,
                {
                    "crew_id": crew.crew_id,
                    "schedule_id": schedule.schedule_id,
                    "phase_id": schedule.phases[0].phase_id,
                },
            )

    def test_cross_tenant_finance_access_is_denied(self) -> None:
        _, _, service, context, _, _, job = job_fixture()
        cost = service.record_job_cost(context, job.job_id, MATERIAL_COST_PAYLOAD)
        invoice = service.create_invoice(
            context,
            {**INVOICE_PAYLOAD, "job_id": job.job_id},
        )
        other = TenantContext("tenant-b", "org-b", "owner-b", ())
        with self.assertRaises(AuthorizationError):
            service.replay_job_cost(other, cost.cost_record_id)
        with self.assertRaises(AuthorizationError):
            service.get_invoice(other, invoice.invoice_id)
        with self.assertRaises(AuthorizationError):
            service.job_profitability(other, job.job_id)

    def test_cross_tenant_crm_and_portal_access_is_denied(self) -> None:
        _, _, service, context, _, proposal, job = job_fixture()
        lead = service.create_lead(context, LEAD_PAYLOAD)
        service.record_customer_message(
            context,
            {
                "customer_id": proposal.customer.customer_id,
                "job_id": job.job_id,
                "channel": "portal",
                "message_date": "2026-08-10",
                "body": "Project update.",
            },
        )
        other = TenantContext("tenant-b", "org-b", "owner-b", ())
        with self.assertRaises(AuthorizationError):
            service.get_lead(other, lead.lead_id)
        with self.assertRaises(AuthorizationError):
            service.customer_portal_view(
                other,
                proposal.customer.customer_id,
                "2026-08-10",
            )
        with self.assertRaises(AuthorizationError):
            service.customer_job_status(other, job.job_id, "2026-08-10")
