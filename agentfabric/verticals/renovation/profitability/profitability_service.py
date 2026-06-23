"""Deterministic profitability and cash-flow calculations."""

from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
import json

from agentfabric.verticals.renovation.finance import JobCostRecord
from agentfabric.verticals.renovation.invoicing import Invoice, VendorPayable

from .models import (
    CashFlowForecast,
    CashFlowWindow,
    CostOverrunAlert,
    MarginVariance,
    ProfitabilityScorecard,
)


FORECAST_WINDOWS = (7, 14, 30, 60, 90)


class ProfitabilityService:
    def scorecard(
        self,
        tenant_id: str,
        job_id: str,
        contracted_revenue: float,
        estimated_cost: float,
        costs: tuple[JobCostRecord, ...],
    ) -> ProfitabilityScorecard:
        revenue = _money(contracted_revenue)
        estimate = _money(estimated_cost)
        actual = _money(sum(item.amount for item in costs))
        estimated_profit = _money(revenue - estimate)
        actual_profit = _money(revenue - actual)
        estimated_margin = _percentage(estimated_profit, revenue)
        actual_margin = _percentage(actual_profit, revenue)
        variance_points = round(actual_margin - estimated_margin, 2)
        margin_variance = None
        if variance_points < 0:
            variance_identity = {
                "job_id": job_id,
                "estimated_margin": estimated_margin,
                "actual_margin": actual_margin,
            }
            margin_variance = MarginVariance(
                variance_id=f"margin-{_digest(variance_identity)[:20]}",
                job_id=job_id,
                estimated_margin_percentage=estimated_margin,
                actual_margin_percentage=actual_margin,
                variance_percentage_points=variance_points,
                severity=_severity(abs(variance_points), 5, 10, 20),
            )
        overrun = _money(max(0, actual - estimate))
        overrun_alert = None
        if overrun:
            overrun_percentage = _percentage(overrun, estimate)
            overrun_identity = {
                "job_id": job_id,
                "estimated_cost": estimate,
                "actual_cost": actual,
            }
            overrun_alert = CostOverrunAlert(
                alert_id=f"overrun-{_digest(overrun_identity)[:20]}",
                job_id=job_id,
                estimated_cost=estimate,
                actual_cost=actual,
                overrun_amount=overrun,
                overrun_percentage=overrun_percentage,
                severity=_severity(overrun_percentage, 5, 10, 20),
            )
        score = max(
            0.0,
            min(
                100.0,
                round(
                    70
                    + min(20, actual_margin / 2)
                    - max(0, -variance_points)
                    - (overrun_alert.overrun_percentage if overrun_alert else 0),
                    2,
                ),
            ),
        )
        identity = {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "contracted_revenue": revenue,
            "estimated_cost": estimate,
            "actual_cost": actual,
            "cost_ids": sorted(item.cost_record_id for item in costs),
        }
        scorecard_id = f"scorecard-{_digest(identity)[:20]}"
        value = {
            "scorecard_id": scorecard_id,
            "tenant_id": tenant_id,
            "job_id": job_id,
            "contracted_revenue": revenue,
            "estimated_cost": estimate,
            "actual_cost": actual,
            "estimated_gross_profit": estimated_profit,
            "actual_gross_profit": actual_profit,
            "estimated_margin_percentage": estimated_margin,
            "actual_margin_percentage": actual_margin,
            "cost_variance": _money(actual - estimate),
            "profitability_score": score,
            "margin_variance": margin_variance.as_dict() if margin_variance else None,
            "cost_overrun_alert": overrun_alert.as_dict() if overrun_alert else None,
        }
        return ProfitabilityScorecard(
            margin_variance=margin_variance,
            cost_overrun_alert=overrun_alert,
            financial_hash=_digest(value),
            **{key: item for key, item in value.items() if key not in {
                "margin_variance", "cost_overrun_alert"
            }},
        )

    def forecast(
        self,
        tenant_id: str,
        as_of_date: str,
        invoices: tuple[Invoice, ...],
        payables: tuple[VendorPayable, ...],
    ) -> CashFlowForecast:
        as_of = date.fromisoformat(as_of_date)
        open_invoices = tuple(item for item in invoices if item.outstanding_balance > 0)
        open_payables = tuple(item for item in payables if item.outstanding_balance > 0)
        overdue_receivables = _money(
            sum(
                item.outstanding_balance
                for item in open_invoices
                if date.fromisoformat(item.due_date) < as_of
            )
        )
        overdue_payables = _money(
            sum(
                item.outstanding_balance
                for item in open_payables
                if date.fromisoformat(item.due_date) < as_of
            )
        )
        windows: list[CashFlowWindow] = []
        previous_days = 0
        cumulative = _money(overdue_receivables - overdue_payables)
        for days in FORECAST_WINDOWS:
            lower = as_of + timedelta(days=previous_days)
            upper = as_of + timedelta(days=days)
            receivables = _money(
                sum(
                    item.outstanding_balance
                    for item in open_invoices
                    if lower <= date.fromisoformat(item.due_date) <= upper
                )
            )
            payable_total = _money(
                sum(
                    item.outstanding_balance
                    for item in open_payables
                    if lower <= date.fromisoformat(item.due_date) <= upper
                )
            )
            net = _money(receivables - payable_total)
            cumulative = _money(cumulative + net)
            windows.append(
                CashFlowWindow(
                    days=days,
                    through_date=upper.isoformat(),
                    receivables=receivables,
                    payables=payable_total,
                    net_cash_flow=net,
                    cumulative_net_cash_flow=cumulative,
                )
            )
            previous_days = days + 1
        identity = {
            "tenant_id": tenant_id,
            "as_of_date": as_of.isoformat(),
            "invoice_balances": sorted(
                (item.invoice_id, item.outstanding_balance, item.due_date)
                for item in open_invoices
            ),
            "payable_balances": sorted(
                (item.payable_id, item.outstanding_balance, item.due_date)
                for item in open_payables
            ),
        }
        value = {
            "forecast_id": f"forecast-{_digest(identity)[:20]}",
            "tenant_id": tenant_id,
            "as_of_date": as_of.isoformat(),
            "windows": [item.as_dict() for item in windows],
            "overdue_receivables": overdue_receivables,
            "overdue_payables": overdue_payables,
        }
        return CashFlowForecast(
            windows=tuple(windows),
            forecast_hash=_digest(value),
            **{key: item for key, item in value.items() if key != "windows"},
        )


def _money(value: float) -> float:
    return round(float(value), 2)


def _percentage(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator * 100, 2)


def _severity(value: float, warning: float, high: float, critical: float) -> str:
    if value >= critical:
        return "critical"
    if value >= high:
        return "high"
    if value >= warning:
        return "warning"
    return "minor"


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
