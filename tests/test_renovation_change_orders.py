from __future__ import annotations

import unittest

from tests.renovation_helpers import CHANGE_ORDER_PAYLOAD, job_fixture


class RenovationChangeOrderTests(unittest.TestCase):
    def test_change_order_price_document_approval_export_and_replay(self) -> None:
        _, _, service, context, _, _, job = job_fixture()
        order = service.create_change_order(
            context,
            {**CHANGE_ORDER_PAYLOAD, "job_id": job.job_id},
        )
        self.assertEqual(order.material_total, 425.0)
        self.assertEqual(order.labor_total, 260.0)
        self.assertEqual(order.subtotal, 685.0)
        self.assertEqual(order.contingency, 68.5)
        self.assertEqual(order.tax, 29.61)
        self.assertEqual(order.total_adjustment, 783.11)
        self.assertIn("Total Adjustment: $783.11", order.rendered_text)
        approved = service.decide_change_order(
            context,
            order.change_order_id,
            "approved",
            {
                "decision_date": "2026-07-09",
                "decided_by": "Jordan Customer",
                "reason": "Approved by signed portal response.",
            },
        )
        self.assertEqual(approved.status, "approved")
        self.assertEqual(len(approved.approval_history), 1)
        self.assertEqual(service.replay_change_order(context, order.change_order_id), approved)
        exported = service.export_change_order(context, order.change_order_id, "text")
        self.assertEqual(exported["template_id"], "change_order_standard")
        self.assertEqual(len(exported["artifact_hash"]), 64)
        with self.assertRaises(ValueError):
            service.decide_change_order(
                context,
                order.change_order_id,
                "rejected",
                {"decision_date": "2026-07-10"},
            )

    def test_rejection_flow_and_deterministic_creation(self) -> None:
        _, _, service, context, _, _, job = job_fixture()
        payload = {**CHANGE_ORDER_PAYLOAD, "job_id": job.job_id}
        first = service.create_change_order(context, payload)
        second = service.create_change_order(context, payload)
        self.assertEqual(first.export_json(), second.export_json())
        rejected = service.decide_change_order(
            context,
            first.change_order_id,
            "rejected",
            {
                "decision_date": "2026-07-09",
                "decided_by": "Jordan Customer",
                "reason": "Budget declined.",
            },
        )
        self.assertEqual(rejected.status, "rejected")
