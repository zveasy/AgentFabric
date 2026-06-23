from __future__ import annotations

import unittest

from agentfabric.audit_bundle import AuditBundleExporter

from tests.renovation_helpers import (
    INVOICE_PAYLOAD,
    MATERIAL_COST_PAYLOAD,
    PAYABLE_PAYLOAD,
    job_fixture,
)


class RenovationFinanceEventTests(unittest.TestCase):
    def test_finance_events_and_audit_bundle(self) -> None:
        persistence, events, service, context, _, _, job = job_fixture()
        service.record_job_cost(context, job.job_id, MATERIAL_COST_PAYLOAD)
        service.record_job_cost(
            context,
            job.job_id,
            {
                "cost_date": "2026-07-20",
                "category": "subcontractor",
                "description": "Remediation",
                "vendor": "Specialist Co",
                "amount": 50000,
            },
        )
        invoice = service.create_invoice(
            context,
            {**INVOICE_PAYLOAD, "job_id": job.job_id},
        )
        service.pay_invoice(
            context,
            invoice.invoice_id,
            {"payment_date": "2026-07-05", "amount": 1000},
        )
        payable = service.create_payable(
            context,
            {**PAYABLE_PAYLOAD, "job_id": job.job_id},
        )
        service.pay_payable(
            context,
            payable.payable_id,
            {"payment_date": "2026-07-06", "amount": 500},
        )
        service.job_profitability(context, job.job_id)
        service.cash_flow_forecast(context, "2026-07-01")
        service.owner_financial_summary(context, "2026-07-01")
        event_types = {event.event_type for event in events.replay()}
        for event_type in {
            "renovation.job_cost_recorded",
            "renovation.invoice_created",
            "renovation.invoice_paid",
            "renovation.payable_created",
            "renovation.payable_paid",
            "renovation.margin_variance_detected",
            "renovation.cost_overrun_detected",
            "renovation.cash_flow_forecast_generated",
            "renovation.profitability_scorecard_generated",
        }:
            self.assertIn(event_type, event_types)
        self.assertTrue(events.validate_integrity())
        bundle = AuditBundleExporter(
            persistence=persistence,
            event_store=events,
        ).export("tenant-a").as_dict()
        for key in {
            "renovation_job_costs",
            "renovation_invoices",
            "renovation_payments",
            "renovation_payables",
            "renovation_profitability_scorecards",
            "renovation_margin_variances",
            "renovation_cost_overrun_alerts",
            "renovation_cash_flow_forecasts",
            "renovation_owner_summaries",
        }:
            self.assertTrue(bundle[key], key)
