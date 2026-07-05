from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.server.app import create_app
from agentfabric.server.config import Settings

from tests.renovation_helpers import (
    AVAILABILITY_PAYLOAD,
    CHANGE_ORDER_PAYLOAD,
    CREW_PAYLOAD,
    DAILY_LOG_PAYLOAD,
    DELIVERY_PAYLOAD,
    ESTIMATE_PAYLOAD,
    FIELD_NOTE_PAYLOAD,
    JOB_PAYLOAD,
    INVOICE_PAYLOAD,
    LEAD_PAYLOAD,
    MATERIAL_COST_PAYLOAD,
    PAYABLE_PAYLOAD,
    OPPORTUNITY_PAYLOAD,
    PROPOSAL_PAYLOAD,
    SCHEDULE_PAYLOAD,
)


class RenovationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.client = TestClient(
            create_app(
                Settings(
                    database_url=f"sqlite:///{Path(self.tmp.name) / 'api.db'}",
                    jwt_secret="test-secret",
                    bootstrap_token="bootstrap-test-token",
                    cloud_queue_backend="memory",
                    rate_limit_auth_per_minute=1000,
                    renovation_storage_dir=str(Path(self.tmp.name) / "renovation-files"),
                )
            )
        )
        self.headers = self._principal("owner-a", "tenant-a", "owner")
        response = self.client.post(
            "/tenants",
            json={
                "tenant_id": "tenant-a",
                "organization_id": "org-a",
                "name": "Tenant A",
                "billing_plan": "enterprise",
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _principal(self, principal_id: str, tenant_id: str, role: str) -> dict[str, str]:
        headers = self.headers if hasattr(self, "headers") else {
            "X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"
        }
        self.client.post(
            "/auth/principals/register",
            json={"principal_id": principal_id, "tenant_id": tenant_id, "role": role, "scopes": []},
            headers=headers,
        )
        token = self.client.post(
            "/auth/token/issue",
            json={"principal_id": principal_id},
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        return {"Authorization": f"Bearer {token.json()['access_token']}"}

    def test_authenticated_estimate_proposal_get_and_export_flow(self) -> None:
        self.assertEqual(self.client.post("/renovation/estimate", json=ESTIMATE_PAYLOAD).status_code, 401)
        estimate = self.client.post(
            "/renovation/estimate",
            json=ESTIMATE_PAYLOAD,
            headers=self.headers,
        )
        self.assertEqual(estimate.status_code, 200)
        estimate_id = estimate.json()["estimate_id"]
        self.assertEqual(
            self.client.get(
                f"/renovation/estimate/{estimate_id}",
                headers=self.headers,
            ).status_code,
            200,
        )
        proposal = self.client.post(
            "/renovation/proposal",
            json={**PROPOSAL_PAYLOAD, "estimate_id": estimate_id},
            headers=self.headers,
        )
        self.assertEqual(proposal.status_code, 200)
        proposal_id = proposal.json()["proposal_id"]
        self.assertEqual(
            self.client.get(
                f"/renovation/proposal/{proposal_id}",
                headers=self.headers,
            ).status_code,
            200,
        )
        exported = self.client.post(
            "/renovation/proposal/export",
            json={"proposal_id": proposal_id, "format": "text"},
            headers=self.headers,
        )
        self.assertEqual(exported.status_code, 200)
        self.assertIn("Payment Schedule", exported.json()["content"])

        viewer_headers = self._principal("viewer-a", "tenant-a", "viewer")
        self.assertEqual(
            self.client.get(
                f"/renovation/estimate/{estimate_id}",
                headers=viewer_headers,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/renovation/estimate",
                json=ESTIMATE_PAYLOAD,
                headers=viewer_headers,
            ).status_code,
            403,
        )

    def test_job_documentation_change_order_and_approval_apis(self) -> None:
        estimate_id = self.client.post(
            "/renovation/estimate",
            json=ESTIMATE_PAYLOAD,
            headers=self.headers,
        ).json()["estimate_id"]
        proposal_id = self.client.post(
            "/renovation/proposal",
            json={**PROPOSAL_PAYLOAD, "estimate_id": estimate_id},
            headers=self.headers,
        ).json()["proposal_id"]
        job = self.client.post(
            "/renovation/jobs",
            json={**JOB_PAYLOAD, "proposal_id": proposal_id},
            headers=self.headers,
        )
        self.assertEqual(job.status_code, 200)
        job_id = job.json()["job_id"]
        log = self.client.post(
            f"/renovation/jobs/{job_id}/daily-log",
            json=DAILY_LOG_PAYLOAD,
            headers=self.headers,
        )
        self.assertEqual(log.status_code, 200)
        self.assertEqual(log.json()["daily_summary"]["work_date"], "2026-07-08")
        self.assertEqual(
            self.client.post(
                f"/renovation/jobs/{job_id}/field-note",
                json=FIELD_NOTE_PAYLOAD,
                headers=self.headers,
            ).status_code,
            200,
        )
        order = self.client.post(
            "/renovation/change-orders",
            json={**CHANGE_ORDER_PAYLOAD, "job_id": job_id},
            headers=self.headers,
        )
        self.assertEqual(order.status_code, 200)
        change_order_id = order.json()["change_order_id"]
        viewer = self._principal("viewer-r2", "tenant-a", "viewer")
        self.assertEqual(
            self.client.post(
                f"/renovation/change-orders/{change_order_id}/approve",
                json={"decision_date": "2026-07-09"},
                headers=viewer,
            ).status_code,
            403,
        )
        approved = self.client.post(
            f"/renovation/change-orders/{change_order_id}/approve",
            json={"decision_date": "2026-07-09", "decided_by": "Customer"},
            headers=self.headers,
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "approved")
        self.assertEqual(
            self.client.get(
                f"/renovation/change-orders/{change_order_id}",
                headers=viewer,
            ).status_code,
            200,
        )
        exported = self.client.post(
            f"/renovation/change-orders/{change_order_id}/export",
            json={"format": "text"},
            headers=self.headers,
        )
        self.assertEqual(exported.status_code, 200)
        self.assertIn("Change Order", exported.json()["content"])
        history = self.client.get(
            f"/renovation/jobs/{job_id}",
            headers=self.headers,
        )
        self.assertEqual(history.status_code, 200)
        self.assertTrue(history.json()["history"]["change_orders"])

    def test_schedule_crew_delivery_and_summary_apis(self) -> None:
        estimate_id = self.client.post(
            "/renovation/estimate",
            json=ESTIMATE_PAYLOAD,
            headers=self.headers,
        ).json()["estimate_id"]
        proposal_id = self.client.post(
            "/renovation/proposal",
            json={**PROPOSAL_PAYLOAD, "estimate_id": estimate_id},
            headers=self.headers,
        ).json()["proposal_id"]
        job_id = self.client.post(
            "/renovation/jobs",
            json={**JOB_PAYLOAD, "proposal_id": proposal_id},
            headers=self.headers,
        ).json()["job_id"]
        schedule_response = self.client.post(
            "/renovation/schedules",
            json={**SCHEDULE_PAYLOAD, "job_id": job_id},
            headers=self.headers,
        )
        self.assertEqual(schedule_response.status_code, 200)
        schedule = schedule_response.json()
        crew_response = self.client.post(
            "/renovation/crews",
            json=CREW_PAYLOAD,
            headers=self.headers,
        )
        self.assertEqual(crew_response.status_code, 200)
        crew_id = crew_response.json()["crew_id"]
        self.assertEqual(
            self.client.post(
                f"/renovation/crews/{crew_id}/availability",
                json=AVAILABILITY_PAYLOAD,
                headers=self.headers,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/renovation/crew-assignments",
                json={
                    "crew_id": crew_id,
                    "schedule_id": schedule["schedule_id"],
                    "phase_id": schedule["phases"][0]["phase_id"],
                },
                headers=self.headers,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/renovation/material-deliveries",
                json={
                    **DELIVERY_PAYLOAD,
                    "schedule_id": schedule["schedule_id"],
                    "phase_id": schedule["phases"][0]["phase_id"],
                },
                headers=self.headers,
            ).status_code,
            200,
        )
        recalculated = self.client.post(
            f"/renovation/schedules/{schedule['schedule_id']}/recalculate",
            json={},
            headers=self.headers,
        )
        self.assertEqual(recalculated.status_code, 200)
        self.assertEqual(recalculated.json()["status"], "delayed")
        self.assertEqual(
            self.client.get(
                f"/renovation/schedules/{schedule['schedule_id']}",
                headers=self.headers,
            ).status_code,
            200,
        )
        summary = self.client.get(
            f"/renovation/jobs/{job_id}/schedule-summary",
            headers=self.headers,
        )
        self.assertEqual(summary.status_code, 200)
        self.assertTrue(summary.json()["summary_hash"])
        viewer = self._principal("viewer-r3", "tenant-a", "viewer")
        self.assertEqual(
            self.client.get(
                f"/renovation/crews/{crew_id}",
                headers=viewer,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/renovation/crews",
                json=CREW_PAYLOAD,
                headers=viewer,
            ).status_code,
            403,
        )

    def test_finance_profitability_invoice_payable_and_cashflow_apis(self) -> None:
        estimate_id = self.client.post(
            "/renovation/estimate",
            json=ESTIMATE_PAYLOAD,
            headers=self.headers,
        ).json()["estimate_id"]
        proposal_id = self.client.post(
            "/renovation/proposal",
            json={**PROPOSAL_PAYLOAD, "estimate_id": estimate_id},
            headers=self.headers,
        ).json()["proposal_id"]
        job_id = self.client.post(
            "/renovation/jobs",
            json={**JOB_PAYLOAD, "proposal_id": proposal_id},
            headers=self.headers,
        ).json()["job_id"]
        cost = self.client.post(
            f"/renovation/jobs/{job_id}/costs",
            json=MATERIAL_COST_PAYLOAD,
            headers=self.headers,
        )
        self.assertEqual(cost.status_code, 200)
        profitability = self.client.get(
            f"/renovation/jobs/{job_id}/profitability",
            headers=self.headers,
        )
        self.assertEqual(profitability.status_code, 200)
        self.assertTrue(profitability.json()["financial_hash"])
        invoice_response = self.client.post(
            "/renovation/invoices",
            json={**INVOICE_PAYLOAD, "job_id": job_id},
            headers=self.headers,
        )
        self.assertEqual(invoice_response.status_code, 200)
        invoice_id = invoice_response.json()["invoice_id"]
        paid = self.client.post(
            f"/renovation/invoices/{invoice_id}/payment",
            json={"payment_date": "2026-07-05", "amount": 1000, "method": "ach"},
            headers=self.headers,
        )
        self.assertEqual(paid.status_code, 200)
        self.assertEqual(paid.json()["outstanding_balance"], 4000)
        self.assertEqual(
            self.client.get(
                f"/renovation/invoices/{invoice_id}",
                headers=self.headers,
            ).status_code,
            200,
        )
        payable_response = self.client.post(
            "/renovation/payables",
            json={**PAYABLE_PAYLOAD, "job_id": job_id},
            headers=self.headers,
        )
        self.assertEqual(payable_response.status_code, 200)
        payable_id = payable_response.json()["payable_id"]
        self.assertEqual(
            self.client.post(
                f"/renovation/payables/{payable_id}/payment",
                json={"payment_date": "2026-07-06", "amount": 500},
                headers=self.headers,
            ).status_code,
            200,
        )
        forecast = self.client.get(
            "/renovation/cash-flow/forecast",
            params={"as_of": "2026-07-01"},
            headers=self.headers,
        )
        self.assertEqual(forecast.status_code, 200)
        self.assertEqual(len(forecast.json()["windows"]), 5)
        owner_summary = self.client.get(
            "/renovation/owner-summary",
            params={"as_of": "2026-07-01"},
            headers=self.headers,
        )
        self.assertEqual(owner_summary.status_code, 200)
        viewer = self._principal("viewer-r4", "tenant-a", "viewer")
        self.assertEqual(
            self.client.get(
                f"/renovation/invoices/{invoice_id}",
                headers=viewer,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/renovation/jobs/{job_id}/costs",
                json=MATERIAL_COST_PAYLOAD,
                headers=viewer,
            ).status_code,
            403,
        )

    def test_crm_lead_appointment_message_and_portal_apis(self) -> None:
        lead_response = self.client.post(
            "/renovation/leads",
            json=LEAD_PAYLOAD,
            headers=self.headers,
        )
        self.assertEqual(lead_response.status_code, 200)
        lead_id = lead_response.json()["lead_id"]
        for status in ("contacted", "estimate_scheduled", "proposal_sent", "won"):
            response = self.client.post(
                f"/renovation/leads/{lead_id}/status",
                json={"status": status},
                headers=self.headers,
            )
            self.assertEqual(response.status_code, 200)
        customer = self.client.post(
            f"/renovation/leads/{lead_id}/convert",
            json={},
            headers=self.headers,
        )
        self.assertEqual(customer.status_code, 200)
        customer_id = customer.json()["customer_id"]
        opportunity = self.client.post(
            "/renovation/opportunities",
            json={**OPPORTUNITY_PAYLOAD, "lead_id": lead_id},
            headers=self.headers,
        )
        self.assertEqual(opportunity.status_code, 200)
        opportunity_id = opportunity.json()["opportunity_id"]
        self.assertEqual(
            self.client.post(
                f"/renovation/opportunities/{opportunity_id}/stage",
                json={"stage": "appointment"},
                headers=self.headers,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/renovation/follow-ups",
                json={
                    "lead_id": lead_id,
                    "description": "Call customer",
                    "due_date": "2026-08-05",
                },
                headers=self.headers,
            ).status_code,
            200,
        )
        appointment = self.client.post(
            "/renovation/appointments",
            json={
                "customer_id": customer_id,
                "requested_date": "2026-08-08",
                "property_address": "200 Oak Street",
            },
            headers=self.headers,
        )
        self.assertEqual(appointment.status_code, 200)
        self.assertEqual(
            self.client.post(
                "/renovation/site-visits",
                json={
                    "appointment_id": appointment.json()["appointment_id"],
                    "visit_date": "2026-08-08",
                    "visited_by": "Estimator",
                    "summary": "Site visit complete.",
                },
                headers=self.headers,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                f"/renovation/leads/{lead_id}",
                headers=self.headers,
            ).status_code,
            200,
        )

        estimate_id = self.client.post(
            "/renovation/estimate",
            json=ESTIMATE_PAYLOAD,
            headers=self.headers,
        ).json()["estimate_id"]
        proposal = self.client.post(
            "/renovation/proposal",
            json={**PROPOSAL_PAYLOAD, "estimate_id": estimate_id},
            headers=self.headers,
        ).json()
        job_id = self.client.post(
            "/renovation/jobs",
            json={**JOB_PAYLOAD, "proposal_id": proposal["proposal_id"]},
            headers=self.headers,
        ).json()["job_id"]
        self.assertEqual(
            self.client.post(
                "/renovation/customer-messages",
                json={
                    "customer_id": proposal["customer"]["customer_id"],
                    "job_id": job_id,
                    "channel": "portal",
                    "message_date": "2026-08-10",
                    "body": "Project update.",
                },
                headers=self.headers,
            ).status_code,
            200,
        )
        portal = self.client.get(
            f"/renovation/customers/{proposal['customer']['customer_id']}/portal-view",
            params={"generated_date": "2026-08-10"},
            headers=self.headers,
        )
        self.assertEqual(portal.status_code, 200)
        self.assertEqual(
            self.client.get(
                f"/renovation/jobs/{job_id}/customer-status",
                params={"generated_date": "2026-08-10"},
                headers=self.headers,
            ).status_code,
            200,
        )
        viewer = self._principal("viewer-r5", "tenant-a", "viewer")
        self.assertEqual(
            self.client.get(
                f"/renovation/leads/{lead_id}",
                headers=viewer,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/renovation/leads",
                json=LEAD_PAYLOAD,
                headers=viewer,
            ).status_code,
            403,
        )

    def test_operator_cockpit_records_metrics_rbac_and_audit_events(self) -> None:
        customer = self.client.post(
            "/renovation/customers",
            json={
                "customer_id": "customer-cockpit-1",
                "name": "Casey Homeowner",
                "email": "casey@example.com",
                "phone": "555-0160",
                "address": "300 Pine Street",
            },
            headers=self.headers,
        )
        self.assertEqual(customer.status_code, 200)
        self.assertEqual(customer.json()["artifact"]["customer_id"], "customer-cockpit-1")
        self.assertIn("created_at", customer.json())
        self.assertEqual(
            self.client.get(
                "/renovation/customers/customer-cockpit-1",
                headers=self.headers,
            ).status_code,
            200,
        )

        lead = self.client.post(
            "/renovation/leads",
            json=LEAD_PAYLOAD,
            headers=self.headers,
        )
        self.assertEqual(lead.status_code, 200)
        lead_id = lead.json()["lead_id"]
        for lead_status in ("contacted", "estimate_scheduled", "proposal_sent", "won"):
            self.assertEqual(
                self.client.post(
                    f"/renovation/leads/{lead_id}/status",
                    json={"status": lead_status},
                    headers=self.headers,
                ).status_code,
                200,
            )
        converted = self.client.post(
            f"/renovation/leads/{lead_id}/convert",
            json={},
            headers=self.headers,
        )
        self.assertEqual(converted.status_code, 200)
        self.assertEqual(
            self.client.get("/renovation/leads", headers=self.headers).json()["total"],
            1,
        )

        estimate = self.client.post(
            "/renovation/estimates",
            json=ESTIMATE_PAYLOAD,
            headers=self.headers,
        )
        self.assertEqual(estimate.status_code, 200)
        estimate_id = estimate.json()["artifact"]["estimate_id"]
        approved = self.client.post(
            f"/renovation/estimates/{estimate_id}/approve",
            json={},
            headers=self.headers,
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "approved")
        self.assertEqual(
            self.client.get(
                f"/renovation/estimates/{estimate_id}",
                headers=self.headers,
            ).status_code,
            200,
        )

        proposal = self.client.post(
            "/renovation/proposals",
            json={**PROPOSAL_PAYLOAD, "estimate_id": estimate_id},
            headers=self.headers,
        )
        self.assertEqual(proposal.status_code, 200)
        proposal_id = proposal.json()["artifact"]["proposal_id"]
        accepted = self.client.post(
            f"/renovation/proposals/{proposal_id}/accept",
            json={"accepted_by": "Casey Homeowner"},
            headers=self.headers,
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["status"], "accepted")

        job = self.client.post(
            "/renovation/jobs",
            json={**JOB_PAYLOAD, "proposal_id": proposal_id},
            headers=self.headers,
        )
        self.assertEqual(job.status_code, 200)
        job_id = job.json()["job_id"]
        status = self.client.patch(
            f"/renovation/jobs/{job_id}/status",
            json={"status": "planned"},
            headers=self.headers,
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["artifact"]["status"], "planned")
        self.assertGreaterEqual(
            self.client.get("/renovation/jobs", headers=self.headers).json()["total"],
            1,
        )

        schedule = self.client.post(
            f"/renovation/jobs/{job_id}/schedule",
            json=SCHEDULE_PAYLOAD,
            headers=self.headers,
        )
        self.assertEqual(schedule.status_code, 200)
        self.assertEqual(
            self.client.get(
                f"/renovation/jobs/{job_id}/schedule",
                headers=self.headers,
            ).json()["total"],
            1,
        )
        cost = self.client.post(
            f"/renovation/jobs/{job_id}/costs",
            json=MATERIAL_COST_PAYLOAD,
            headers=self.headers,
        )
        self.assertEqual(cost.status_code, 200)
        self.assertEqual(
            self.client.get(
                f"/renovation/jobs/{job_id}/costs",
                headers=self.headers,
            ).json()["total"],
            1,
        )
        self.assertEqual(
            self.client.get(
                f"/renovation/jobs/{job_id}/profitability",
                headers=self.headers,
            ).status_code,
            200,
        )

        invoice = self.client.post(
            f"/renovation/jobs/{job_id}/invoices",
            json=INVOICE_PAYLOAD,
            headers=self.headers,
        )
        self.assertEqual(invoice.status_code, 200)
        invoice_id = invoice.json()["artifact"]["invoice_id"]
        self.assertEqual(
            self.client.get(
                f"/renovation/jobs/{job_id}/invoices",
                headers=self.headers,
            ).json()["total"],
            1,
        )
        payment = self.client.post(
            f"/renovation/invoices/{invoice_id}/payments",
            json={"payment_date": "2026-07-05", "amount": 1000, "method": "ach"},
            headers=self.headers,
        )
        self.assertEqual(payment.status_code, 200)
        self.assertEqual(payment.json()["artifact"]["paid_amount"], 1000)

        self.assertEqual(
            self.client.post(
                "/renovation/customer-messages",
                json={
                    "customer_id": PROPOSAL_PAYLOAD["customer"]["customer_id"],
                    "job_id": job_id,
                    "channel": "portal",
                    "message_date": "2026-08-10",
                    "body": "Project update.",
                },
                headers=self.headers,
            ).status_code,
            200,
        )
        portal = self.client.get(
            f"/renovation/jobs/{job_id}/portal",
            headers=self.headers,
        )
        self.assertEqual(portal.status_code, 200)

        metrics = self.client.get("/renovation/metrics", headers=self.headers)
        self.assertEqual(metrics.status_code, 200)
        self.assertEqual(metrics.json()["total_leads"], 1)
        self.assertEqual(metrics.json()["converted_leads"], 1)
        self.assertGreater(metrics.json()["estimated_revenue"], 0)
        self.assertEqual(metrics.json()["invoiced_revenue"], 5000)
        self.assertEqual(metrics.json()["paid_revenue"], 1000)

        viewer = self._principal("viewer-operator", "tenant-a", "viewer")
        self.assertEqual(
            self.client.get("/renovation/metrics", headers=viewer).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/renovation/customers",
                json={"name": "Read Only"},
                headers=viewer,
            ).status_code,
            403,
        )
        missing = self.client.get(
            "/renovation/customers/does-not-exist",
            headers=self.headers,
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["error"]["code"], "not_found")

        events = self.client.get("/events", headers=self.headers)
        self.assertEqual(events.status_code, 200)
        event_types = {event["event_type"] for event in events.json()["items"]}
        self.assertTrue(
            {
                "renovation.operator.customer.created",
                "renovation.operator.lead.created",
                "renovation.operator.lead.converted",
                "renovation.operator.estimate.created",
                "renovation.operator.estimate.approved",
                "renovation.operator.proposal.created",
                "renovation.operator.proposal.accepted",
                "renovation.operator.job.created",
                "renovation.operator.job.status_changed",
                "renovation.operator.schedule_item.created",
                "renovation.operator.cost_item.created",
                "renovation.operator.invoice.created",
                "renovation.operator.payment.recorded",
                "renovation.operator.portal.viewed",
                "renovation.operator.metrics.viewed",
            }.issubset(event_types)
        )

    def test_mvp_demo_workflow_is_durable_across_app_recreation(self) -> None:
        app_shell = self.client.get("/renovation/app")
        self.assertEqual(app_shell.status_code, 200)
        self.assertIn("Operator cockpit", app_shell.text)

        response = self.client.post(
            "/renovation/mvp/demo",
            json={"idempotency_key": "mvp-test-001"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["status"], "completed")
        run_id = result["run_id"]
        job_id = result["entity_ids"]["job_id"]
        self.assertTrue(result["portal"]["view_hash"])
        self.assertEqual(
            result["steps"]["invoice_payment"]["output"]["invoice"]["outstanding_balance"],
            4000,
        )

        duplicate = self.client.post(
            "/renovation/mvp/runs",
            json={"idempotency_key": "mvp-test-001"},
            headers=self.headers,
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.json()["run_id"], run_id)

        restarted = TestClient(
            create_app(
                Settings(
                    database_url=f"sqlite:///{Path(self.tmp.name) / 'api.db'}",
                    jwt_secret="test-secret",
                    bootstrap_token="bootstrap-test-token",
                    cloud_queue_backend="memory",
                    rate_limit_auth_per_minute=1000,
                )
            )
        )
        persisted = restarted.get(
            f"/renovation/jobs/{job_id}",
            headers=self.headers,
        )
        self.assertEqual(persisted.status_code, 200)
        self.assertEqual(persisted.json()["job_id"], job_id)
        run = restarted.get(
            f"/renovation/mvp/runs/{run_id}",
            headers=self.headers,
        )
        self.assertEqual(run.status_code, 200)
        self.assertEqual(run.json()["entity_ids"]["job_id"], job_id)
        portal = restarted.get(
            f"/renovation/mvp/runs/{run_id}/portal",
            headers=self.headers,
        )
        self.assertEqual(portal.status_code, 200)
        self.assertTrue(portal.json()["portal"]["view_hash"])
        replay = restarted.post(
            f"/renovation/mvp/runs/{run_id}/replay",
            json={},
            headers=self.headers,
        )
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["replay_count"], 1)

        viewer = self._principal("viewer-mvp", "tenant-a", "viewer")
        self.assertEqual(
            restarted.get("/renovation/mvp/runs", headers=viewer).status_code,
            200,
        )
        self.assertEqual(
            restarted.post("/renovation/mvp/runs", json={}, headers=viewer).status_code,
            403,
        )

    def test_saas_readiness_pdf_files_providers_roles_and_tenant_isolation(self) -> None:
        account = self.client.get("/renovation/account", headers=self.headers)
        self.assertEqual(account.status_code, 200)
        self.assertTrue(account.json()["permissions"]["can_manage"])

        assigned = self.client.post(
            "/renovation/accounts/roles",
            json={
                "account_id": "operator-b",
                "principal_id": "operator-b",
                "name": "Operator B",
                "email": "operator@example.com",
                "role": "operator",
            },
            headers=self.headers,
        )
        self.assertEqual(assigned.status_code, 200)
        self.assertEqual(assigned.json()["artifact"]["role"], "operator")
        self.assertEqual(self.client.get("/renovation/accounts", headers=self.headers).json()["total"], 1)
        bridged_token = self.client.post(
            "/auth/token/issue",
            json={"principal_id": "operator-b"},
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        self.assertEqual(bridged_token.status_code, 200)
        bridged_headers = {"Authorization": f"Bearer {bridged_token.json()['access_token']}"}
        bridged_account = self.client.get("/renovation/account", headers=bridged_headers)
        self.assertEqual(bridged_account.status_code, 200)
        self.assertEqual(bridged_account.json()["role"], "operator")

        operator_headers = self._principal("operator-b", "tenant-a", "operator")
        viewer_headers = self._principal("viewer-saas", "tenant-a", "viewer")
        self.assertEqual(
            self.client.post(
                "/renovation/accounts/roles",
                json={"account_id": "viewer-saas", "role": "viewer"},
                headers=operator_headers,
            ).status_code,
            403,
        )

        estimate = self.client.post("/renovation/estimates", json=ESTIMATE_PAYLOAD, headers=self.headers)
        self.assertEqual(estimate.status_code, 200)
        estimate_id = estimate.json()["artifact"]["estimate_id"]
        proposal = self.client.post(
            "/renovation/proposals",
            json={**PROPOSAL_PAYLOAD, "estimate_id": estimate_id},
            headers=self.headers,
        )
        self.assertEqual(proposal.status_code, 200)
        proposal_id = proposal.json()["artifact"]["proposal_id"]
        branded = self.client.patch(
            "/renovation/settings/company",
            json={
                "company_name": "Casey Renovations",
                "email": "office@casey.example",
                "proposal_terms": "Signature required before work begins.",
                "invoice_terms": "Due on receipt.",
            },
            headers=self.headers,
        )
        self.assertEqual(branded.status_code, 200)
        self.assertEqual(branded.json()["artifact"]["company_name"], "Casey Renovations")
        pdf = self.client.get(f"/renovation/proposals/{proposal_id}/pdf", headers=self.headers)
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf.headers["content-type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF-1.4"))
        self.assertIn(b"RenovationOS Proposal", pdf.content)
        self.assertIn(b"Casey Renovations", pdf.content)

        uploaded = self.client.post(
            f"/renovation/files/proposal/{proposal_id}",
            files={"file": ("proposal-note.txt", b"signed scope note", "text/plain")},
            headers=self.headers,
        )
        self.assertEqual(uploaded.status_code, 200)
        uploaded_artifact = uploaded.json()["artifact"]
        attachment_id = uploaded_artifact["attachment_id"]
        self.assertEqual(uploaded_artifact["entity_type"], "proposal")
        self.assertEqual(uploaded_artifact["entity_id"], proposal_id)
        self.assertTrue(Path(uploaded_artifact["storage_path"]).exists())
        downloaded = self.client.get(f"/renovation/files/{attachment_id}", headers=self.headers)
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, b"signed scope note")
        self.assertEqual(
            self.client.post(
                f"/renovation/files/proposal/{proposal_id}",
                files={"file": ("blocked.exe", b"no", "application/x-msdownload")},
                headers=self.headers,
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                "/renovation/files",
                params={"entity_type": "proposal", "entity_id": proposal_id},
                headers=self.headers,
            ).json()["total"],
            1,
        )
        self.assertEqual(
            self.client.post(
                f"/renovation/files/proposal/{proposal_id}",
                files={"file": ("readonly.txt", b"no", "text/plain")},
                headers=viewer_headers,
            ).status_code,
            403,
        )
        archived = self.client.delete(f"/renovation/files/{attachment_id}", headers=self.headers)
        self.assertEqual(archived.status_code, 200)
        self.assertEqual(archived.json()["artifact"]["status"], "archived")
        self.assertEqual(self.client.get(f"/renovation/files/{attachment_id}", headers=self.headers).status_code, 404)
        self.assertEqual(
            self.client.get(
                "/renovation/files",
                params={"entity_type": "proposal", "entity_id": proposal_id, "include_archived": True},
                headers=self.headers,
            ).json()["total"],
            1,
        )

        accepted = self.client.post(
            f"/renovation/proposals/{proposal_id}/accept",
            json={"accepted_by": "Jordan Customer"},
            headers=self.headers,
        )
        self.assertEqual(accepted.status_code, 200)
        job = self.client.post(
            "/renovation/jobs",
            json={**JOB_PAYLOAD, "proposal_id": proposal_id},
            headers=self.headers,
        )
        self.assertEqual(job.status_code, 200)
        job_id = job.json()["job_id"]
        schedule = self.client.post(
            f"/renovation/jobs/{job_id}/schedule",
            json=SCHEDULE_PAYLOAD,
            headers=self.headers,
        )
        self.assertEqual(schedule.status_code, 200)
        schedule_id = schedule.json()["artifact"]["schedule_id"]
        calendar = self.client.post(f"/renovation/schedule/{schedule_id}/sync", headers=self.headers)
        self.assertEqual(calendar.status_code, 200)
        self.assertEqual(calendar.json()["artifact"]["provider"], "local-calendar")
        google_calendar = self.client.post(
            f"/renovation/schedule/{schedule_id}/sync",
            json={
                "provider": "google",
                "operation": "create",
                "event_title": "Kitchen rough-in",
                "start_time": "2026-07-06T09:00:00Z",
                "end_time": "2026-07-06T12:00:00Z",
            },
            headers=self.headers,
        )
        self.assertEqual(google_calendar.status_code, 200)
        self.assertEqual(google_calendar.json()["artifact"]["provider"], "google-calendar")
        self.assertEqual(google_calendar.json()["artifact"]["payload"]["event_title"], "Kitchen rough-in")
        self.assertEqual(google_calendar.json()["artifact"]["payload"]["sync_status"], "synced")
        updated_calendar = self.client.post(
            f"/renovation/schedule/{schedule_id}/sync",
            json={
                "provider": "outlook",
                "operation": "update",
                "external_event_id": "outlook-event-1",
                "event_title": "Kitchen rough-in updated",
            },
            headers=self.headers,
        )
        self.assertEqual(updated_calendar.status_code, 200)
        self.assertEqual(updated_calendar.json()["artifact"]["provider"], "outlook-calendar")
        self.assertEqual(updated_calendar.json()["artifact"]["payload"]["operation"], "update")
        deleted_calendar = self.client.post(
            f"/renovation/schedule/{schedule_id}/sync",
            json={"provider": "outlook", "operation": "delete", "external_event_id": "outlook-event-1"},
            headers=self.headers,
        )
        self.assertEqual(deleted_calendar.status_code, 200)
        self.assertEqual(deleted_calendar.json()["artifact"]["payload"]["sync_status"], "deleted")
        self.assertIsNone(deleted_calendar.json()["artifact"]["payload"]["external_event_id"])
        failed_calendar = self.client.post(
            f"/renovation/schedule/{schedule_id}/sync",
            json={"provider": "google", "simulate_failure": True, "failure_reason": "missing OAuth consent"},
            headers=self.headers,
        )
        self.assertEqual(failed_calendar.status_code, 200)
        self.assertEqual(failed_calendar.json()["artifact"]["status"], "failed")
        self.assertEqual(failed_calendar.json()["artifact"]["failure_reason"], "missing OAuth consent")

        invoice = self.client.post(
            f"/renovation/jobs/{job_id}/invoices",
            json=INVOICE_PAYLOAD,
            headers=self.headers,
        )
        self.assertEqual(invoice.status_code, 200)
        invoice_id = invoice.json()["artifact"]["invoice_id"]
        payment_link = self.client.post(
            f"/renovation/invoices/{invoice_id}/payment-link",
            json={"idempotency_key": "invoice-link-1"},
            headers=self.headers,
        )
        self.assertEqual(payment_link.status_code, 200)
        self.assertEqual(payment_link.json()["artifact"]["provider"], "local-payment")
        self.assertIn("payment_url", payment_link.json()["artifact"]["payload"])
        stripe_link = self.client.post(
            f"/renovation/invoices/{invoice_id}/payment-link",
            json={"idempotency_key": "stripe-link-1", "provider": "stripe"},
            headers=self.headers,
        )
        self.assertEqual(stripe_link.status_code, 200)
        self.assertEqual(stripe_link.json()["artifact"]["provider"], "stripe-shell")
        self.assertIn("pay.stripe.local", stripe_link.json()["artifact"]["payload"]["payment_url"])
        repeated_stripe_link = self.client.post(
            f"/renovation/invoices/{invoice_id}/payment-link",
            json={"idempotency_key": "stripe-link-1", "provider": "stripe"},
            headers=self.headers,
        )
        self.assertEqual(
            repeated_stripe_link.json()["artifact"]["reference_id"],
            stripe_link.json()["artifact"]["reference_id"],
        )
        repeated_link = self.client.post(
            f"/renovation/invoices/{invoice_id}/payment-link",
            json={"idempotency_key": "invoice-link-1"},
            headers=self.headers,
        )
        self.assertEqual(repeated_link.status_code, 200)
        self.assertEqual(
            repeated_link.json()["artifact"]["reference_id"],
            payment_link.json()["artifact"]["reference_id"],
        )
        invoice_pdf = self.client.get(f"/renovation/invoices/{invoice_id}/pdf", headers=self.headers)
        self.assertEqual(invoice_pdf.status_code, 200)
        self.assertIn(b"RenovationOS Invoice", invoice_pdf.content)
        self.assertIn(b"Invoice balance", invoice_pdf.content)
        payment_status = self.client.post(
            f"/renovation/invoices/{invoice_id}/payment-status",
            json={"status": "pending", "provider_reference_id": "pay-ref-1", "idempotency_key": "status-1"},
            headers=self.headers,
        )
        self.assertEqual(payment_status.status_code, 200)
        self.assertEqual(payment_status.json()["artifact"]["payload"]["payment_status"], "pending")
        webhook = self.client.post(
            "/renovation/payments/webhook",
            json={
                "invoice_id": invoice_id,
                "status": "paid",
                "provider_reference_id": "pay-ref-1",
                "idempotency_key": "webhook-1",
            },
            headers=self.headers,
        )
        self.assertEqual(webhook.status_code, 200)
        self.assertEqual(webhook.json()["artifact"]["payload"]["payment_status"], "paid")
        webhook_replay = self.client.post(
            "/renovation/payments/webhook",
            json={
                "invoice_id": invoice_id,
                "event_type": "checkout.session.completed",
                "provider": "stripe",
                "provider_reference_id": "pay-ref-1",
                "idempotency_key": "webhook-1",
            },
            headers=self.headers,
        )
        self.assertEqual(webhook_replay.status_code, 200)
        self.assertEqual(webhook_replay.json()["artifact"]["reference_id"], webhook.json()["artifact"]["reference_id"])
        mapped_webhook = self.client.post(
            "/renovation/payments/webhook",
            json={
                "invoice_id": invoice_id,
                "event_type": "payment_intent.payment_failed",
                "provider": "stripe",
                "provider_reference_id": "pay-ref-2",
                "idempotency_key": "webhook-failed",
            },
            headers=self.headers,
        )
        self.assertEqual(mapped_webhook.status_code, 200)
        self.assertEqual(mapped_webhook.json()["artifact"]["payload"]["payment_status"], "failed")
        rejected_webhook = self.client.post(
            "/renovation/payments/webhook",
            json={
                "invoice_id": invoice_id,
                "status": "paid",
                "provider": "stripe",
                "provider_reference_id": "pay-ref-1",
                "idempotency_key": "webhook-rejected",
                "signature_valid": False,
            },
            headers=self.headers,
        )
        self.assertEqual(rejected_webhook.status_code, 400)

        notification = self.client.post(
            "/renovation/notifications/proposal_sent",
            json={"proposal_id": proposal_id, "customer_id": PROPOSAL_PAYLOAD["customer"]["customer_id"], "channel": "email"},
            headers=self.headers,
        )
        self.assertEqual(notification.status_code, 200)
        self.assertEqual(notification.json()["artifact"]["provider"], "local-log")
        smtp_notification = self.client.post(
            "/renovation/notifications/proposal_sent",
            json={
                "provider": "smtp",
                "channel": "email",
                "smtp_host": "smtp.casey.example",
                "sender": "office@casey.example",
                "reply_to": "reply@casey.example",
                "recipients": ["customer@example.com"],
                "cc": ["sales@casey.example"],
                "bcc": ["archive@casey.example"],
                "subject": "Your proposal",
                "body": "Proposal attached.",
                "html_body": "<p>Proposal attached.</p>",
            },
            headers=self.headers,
        )
        self.assertEqual(smtp_notification.status_code, 200)
        self.assertEqual(smtp_notification.json()["artifact"]["provider"], "smtp-email")
        self.assertEqual(smtp_notification.json()["artifact"]["status"], "stubbed")
        self.assertEqual(smtp_notification.json()["artifact"]["payload"]["delivery_status"], "stubbed")
        self.assertFalse(smtp_notification.json()["artifact"]["payload"]["live_enabled"])
        self.assertEqual(smtp_notification.json()["artifact"]["payload"]["cc"], ["sales@casey.example"])
        self.assertEqual(smtp_notification.json()["artifact"]["payload"]["bcc"], ["archive@casey.example"])
        failed_smtp = self.client.post(
            "/renovation/notifications/proposal_sent",
            json={
                "provider": "smtp",
                "channel": "email",
                "smtp_host": "smtp.casey.example",
                "sender": "office@casey.example",
                "recipients": ["customer@example.com"],
                "simulate_failure": True,
                "failure_reason": "mailbox unavailable",
            },
            headers=self.headers,
        )
        self.assertEqual(failed_smtp.status_code, 200)
        self.assertEqual(failed_smtp.json()["artifact"]["status"], "failed")
        sms_notification = self.client.post(
            "/renovation/notifications/schedule_changed",
            json={
                "provider": "sms",
                "channel": "sms",
                "sender_id": "RENOS",
                "recipients": ["5550100"],
                "body": "Schedule changed.",
            },
            headers=self.headers,
        )
        self.assertEqual(sms_notification.status_code, 200)
        self.assertEqual(sms_notification.json()["artifact"]["provider"], "sms-shell")
        self.assertEqual(self.client.get("/renovation/notifications", headers=self.headers).json()["total"], 4)
        email_validation = self.client.post(
            "/renovation/integrations/notification/validate",
            json={"provider": "smtp", "channel": "email", "sender": "office@casey.example"},
            headers=self.headers,
        )
        self.assertEqual(email_validation.status_code, 200)
        self.assertFalse(email_validation.json()["valid"])
        smtp_validation = self.client.post(
            "/renovation/integrations/notification/validate",
            json={
                "provider": "smtp",
                "channel": "email",
                "smtp_host": "smtp.casey.example",
                "sender": "office@casey.example",
            },
            headers=self.headers,
        )
        self.assertEqual(smtp_validation.status_code, 200)
        self.assertTrue(smtp_validation.json()["valid"])
        sms_validation = self.client.post(
            "/renovation/integrations/notification/validate",
            json={"provider": "twilio", "channel": "sms", "sender_id": "RENOS"},
            headers=self.headers,
        )
        self.assertEqual(sms_validation.status_code, 200)
        self.assertFalse(sms_validation.json()["valid"])
        self.assertEqual(sms_validation.json()["missing"], ["account_sid", "auth_token"])
        twilio_validation = self.client.post(
            "/renovation/integrations/notification/validate",
            json={
                "provider": "twilio",
                "channel": "sms",
                "sender_id": "RENOS",
                "account_sid": "AC123",
                "auth_token": "secret",
            },
            headers=self.headers,
        )
        self.assertEqual(twilio_validation.status_code, 200)
        self.assertTrue(twilio_validation.json()["valid"])
        self.assertTrue(
            self.client.post(
                "/renovation/integrations/calendar/validate",
                json={"provider": "outlook"},
                headers=self.headers,
            ).json()["valid"]
        )
        self.assertTrue(
            self.client.post(
                "/renovation/integrations/payment/validate",
                json={"provider": "stripe"},
                headers=self.headers,
            ).json()["valid"]
        )
        integrations = self.client.get("/renovation/integrations", headers=self.headers)
        self.assertEqual(integrations.status_code, 200)
        self.assertEqual(integrations.json()["total"], 4)
        self.assertIn("checklist", integrations.json()["items"][0])
        self.assertIn("setup_instructions", integrations.json()["items"][0])
        self.assertEqual(
            self.client.post(
                "/renovation/integrations/notification/validate",
                json={"provider": "smtp", "channel": "email"},
                headers=viewer_headers,
            ).status_code,
            403,
        )
        app_shell = self.client.get("/renovation/app")
        self.assertEqual(app_shell.status_code, 200)
        self.assertIn("Integrations", app_shell.text)
        self.assertIn("/renovation/integrations", app_shell.text)
        self.assertIn("Validate", app_shell.text)
        self.assertIn("Required setup", app_shell.text)
        invalid_provider = self.client.post(
            "/renovation/integrations/unknown/validate",
            json={},
            headers=self.headers,
        )
        self.assertEqual(invalid_provider.status_code, 400)

        events = self.client.get("/events", headers=self.headers)
        event_types = {event["event_type"] for event in events.json()["items"]}
        self.assertTrue(
            {
                "renovation.operator.provider.validated",
                "renovation.operator.provider.failed",
                "renovation.operator.notification.send_attempted",
                "renovation.operator.notification.failed",
                "renovation.operator.calendar.sync_attempted",
                "renovation.operator.payment_link.created",
                "renovation.operator.payment_webhook.received",
                "renovation.operator.payment_webhook.rejected",
            }.issubset(event_types)
        )

        self.assertEqual(
            self.client.get("/renovation/customers/does-not-exist", headers=self.headers).status_code,
            404,
        )
