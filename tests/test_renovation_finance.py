from __future__ import annotations

import unittest

from tests.renovation_helpers import (
    LABOR_COST_PAYLOAD,
    MATERIAL_COST_PAYLOAD,
    OVERHEAD_COST_PAYLOAD,
    job_fixture,
)


class RenovationFinanceTests(unittest.TestCase):
    def test_job_cost_types_estimate_comparison_margin_and_replay(self) -> None:
        _, _, service, context, estimate, _, job = job_fixture()
        material = service.record_job_cost(context, job.job_id, MATERIAL_COST_PAYLOAD)
        labor = service.record_job_cost(context, job.job_id, LABOR_COST_PAYLOAD)
        overhead = service.record_job_cost(context, job.job_id, OVERHEAD_COST_PAYLOAD)
        scorecard = service.job_profitability(context, job.job_id)
        self.assertEqual(material.amount, 9000)
        self.assertEqual(labor.amount, 5600)
        self.assertEqual(overhead.amount, 750)
        self.assertEqual(overhead.overhead.allocation_method, "direct")
        self.assertEqual(
            scorecard.actual_cost,
            material.amount + labor.amount + overhead.amount,
        )
        self.assertEqual(
            scorecard.estimated_cost,
            round(estimate.subtotal + estimate.contingency, 2),
        )
        self.assertEqual(
            scorecard.actual_gross_profit,
            round(scorecard.contracted_revenue - scorecard.actual_cost, 2),
        )
        self.assertEqual(service.replay_job_cost(context, material.cost_record_id), material)
        self.assertEqual(
            service.replay_profitability(context, scorecard.scorecard_id),
            scorecard,
        )

    def test_cost_overrun_and_margin_compression_are_detected(self) -> None:
        _, _, service, context, _, _, job = job_fixture()
        service.record_job_cost(
            context,
            job.job_id,
            {
                "cost_date": "2026-07-20",
                "category": "subcontractor",
                "description": "Emergency remediation",
                "vendor": "Specialist Co",
                "amount": 50000,
            },
        )
        scorecard = service.job_profitability(context, job.job_id)
        self.assertIsNotNone(scorecard.cost_overrun_alert)
        self.assertIsNotNone(scorecard.margin_variance)
        self.assertGreater(scorecard.cost_overrun_alert.overrun_amount, 0)
        self.assertLess(scorecard.margin_variance.variance_percentage_points, 0)

    def test_invalid_and_negative_costs_fail_closed(self) -> None:
        _, _, service, context, _, _, job = job_fixture()
        with self.assertRaises(ValueError):
            service.record_job_cost(
                context,
                job.job_id,
                {
                    "cost_date": "2026-07-10",
                    "category": "material",
                    "description": "Invalid",
                    "quantity": 1,
                    "unit_cost": -1,
                },
            )
