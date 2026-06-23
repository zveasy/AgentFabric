from __future__ import annotations

import unittest

from tests.renovation_helpers import INVOICE_PAYLOAD, PAYABLE_PAYLOAD, job_fixture


class RenovationInvoicingCashFlowTests(unittest.TestCase):
    def test_invoice_payments_balances_and_replay(self) -> None:
        _, _, service, context, _, _, job = job_fixture()
        invoice = service.create_invoice(
            context,
            {**INVOICE_PAYLOAD, "job_id": job.job_id},
        )
        partial = service.pay_invoice(
            context,
            invoice.invoice_id,
            {
                "payment_date": "2026-07-05",
                "amount": 2000,
                "method": "ach",
                "reference": "payment-1",
            },
        )
        self.assertEqual(partial.status, "partial")
        self.assertEqual(partial.outstanding_balance, 3000)
        paid = service.pay_invoice(
            context,
            invoice.invoice_id,
            {
                "payment_date": "2026-07-10",
                "amount": 3000,
                "method": "check",
                "reference": "payment-2",
            },
        )
        self.assertEqual(paid.status, "paid")
        self.assertEqual(paid.outstanding_balance, 0)
        self.assertEqual(service.replay_invoice(context, invoice.invoice_id), paid)
        with self.assertRaises(ValueError):
            service.pay_invoice(
                context,
                invoice.invoice_id,
                {"payment_date": "2026-07-11", "amount": 1},
            )

    def test_vendor_payable_and_payment_replay(self) -> None:
        _, _, service, context, _, _, job = job_fixture()
        payable = service.create_payable(
            context,
            {**PAYABLE_PAYLOAD, "job_id": job.job_id},
        )
        updated = service.pay_payable(
            context,
            payable.payable_id,
            {
                "payment_date": "2026-07-12",
                "amount": 1000,
                "method": "ach",
                "reference": "vendor-payment-1",
            },
        )
        self.assertEqual(updated.status, "partial")
        self.assertEqual(updated.outstanding_balance, 1500)
        self.assertEqual(service.replay_payable(context, payable.payable_id), updated)

    def test_cash_flow_windows_owner_summary_and_replay(self) -> None:
        _, _, service, context, _, _, job = job_fixture()
        service.create_invoice(
            context,
            {
                **INVOICE_PAYLOAD,
                "job_id": job.job_id,
                "due_date": "2026-07-08",
            },
        )
        service.create_payable(
            context,
            {
                **PAYABLE_PAYLOAD,
                "job_id": job.job_id,
                "due_date": "2026-07-20",
            },
        )
        forecast = service.cash_flow_forecast(context, "2026-07-01")
        self.assertEqual([item.days for item in forecast.windows], [7, 14, 30, 60, 90])
        self.assertEqual(forecast.windows[0].receivables, 5000)
        self.assertEqual(forecast.windows[2].payables, 2500)
        self.assertEqual(
            service.replay_cash_flow(context, forecast.forecast_id),
            forecast,
        )
        summary = service.owner_financial_summary(context, "2026-07-01")
        self.assertEqual(summary["job_count"], 1)
        self.assertEqual(summary["outstanding_receivables"], 5000)
        self.assertEqual(summary["outstanding_payables"], 2500)
        self.assertEqual(len(summary["financial_hash"]), 64)
