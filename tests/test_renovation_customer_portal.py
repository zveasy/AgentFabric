from __future__ import annotations

import json
import unittest

from tests.renovation_helpers import (
    CHANGE_ORDER_PAYLOAD,
    INVOICE_PAYLOAD,
    SCHEDULE_PAYLOAD,
    job_fixture,
)


class RenovationCustomerPortalTests(unittest.TestCase):
    def test_messages_portal_visibility_customer_status_and_replay(self) -> None:
        _, _, service, context, _, proposal, job = job_fixture()
        service.create_schedule(
            context,
            {**SCHEDULE_PAYLOAD, "job_id": job.job_id},
        )
        visible_log = {
            "work_date": "2026-08-10",
            "summary": "Cabinet installation completed.",
            "weather": "Clear",
            "crew_hours": 12,
            "completed_work": ["Installed cabinets"],
            "next_steps": ["Template counters"],
            "photos": [
                {
                    "captured_date": "2026-08-10",
                    "file_name": "cabinets.jpg",
                    "storage_reference": "veil:photo:cabinets",
                    "sha256": "c" * 64,
                    "caption": "Installed cabinets",
                    "phase_id": job.phases[0].phase_id,
                    "approved_for_customer": True,
                },
                {
                    "captured_date": "2026-08-10",
                    "file_name": "internal.jpg",
                    "storage_reference": "veil:photo:internal",
                    "sha256": "d" * 64,
                    "caption": "Internal condition",
                    "phase_id": job.phases[0].phase_id,
                    "approved_for_customer": False,
                },
            ],
        }
        service.add_daily_log(context, job.job_id, visible_log)
        service.add_daily_log(
            context,
            job.job_id,
            {
                **visible_log,
                "work_date": "2026-08-11",
                "summary": "Internal quality concern.",
                "internal": True,
                "photos": [],
            },
        )
        order = service.create_change_order(
            context,
            {**CHANGE_ORDER_PAYLOAD, "job_id": job.job_id},
        )
        service.decide_change_order(
            context,
            order.change_order_id,
            "approved",
            {"decision_date": "2026-08-09", "decided_by": "Customer"},
        )
        invoice = service.create_invoice(
            context,
            {**INVOICE_PAYLOAD, "job_id": job.job_id},
        )
        service.pay_invoice(
            context,
            invoice.invoice_id,
            {"payment_date": "2026-08-05", "amount": 1000},
        )
        service.record_customer_message(
            context,
            {
                "customer_id": proposal.customer.customer_id,
                "job_id": job.job_id,
                "channel": "portal",
                "direction": "outbound",
                "message_date": "2026-08-10",
                "subject": "Progress update",
                "body": "Cabinet installation is complete.",
                "visibility": "customer",
            },
        )
        service.record_customer_message(
            context,
            {
                "customer_id": proposal.customer.customer_id,
                "job_id": job.job_id,
                "channel": "note",
                "direction": "internal",
                "message_date": "2026-08-10",
                "body": "Internal escalation note.",
                "visibility": "internal",
            },
        )
        view = service.customer_portal_view(
            context,
            proposal.customer.customer_id,
            "2026-08-12",
        )
        project = view.projects[0]
        encoded = json.dumps(view.as_dict(), sort_keys=True)
        self.assertEqual(len(project["approved_photos"]), 1)
        self.assertEqual(len(project["recent_progress"]), 1)
        self.assertEqual(len(project["approved_change_orders"]), 1)
        self.assertEqual(project["invoice_status"][0]["outstanding_balance"], 4000)
        self.assertEqual(len(view.communications), 1)
        for forbidden in (
            "profitability",
            "margin",
            "vendor",
            "schedule_hash",
            "history_hash",
            "cost_overrun",
            "created_by",
        ):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(
            service.replay_customer_portal_view(context, view.portal_view_id),
            view,
        )
        status = service.customer_job_status(context, job.job_id, "2026-08-12")
        self.assertEqual(status["project"]["job_id"], job.job_id)
