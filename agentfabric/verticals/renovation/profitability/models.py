"""Profitability and cash-flow models."""

from dataclasses import dataclass

from agentfabric.verticals.renovation.models.base import SerializableModel


@dataclass(frozen=True)
class MarginVariance(SerializableModel):
    variance_id: str
    job_id: str
    estimated_margin_percentage: float
    actual_margin_percentage: float
    variance_percentage_points: float
    severity: str


@dataclass(frozen=True)
class CostOverrunAlert(SerializableModel):
    alert_id: str
    job_id: str
    estimated_cost: float
    actual_cost: float
    overrun_amount: float
    overrun_percentage: float
    severity: str


@dataclass(frozen=True)
class ProfitabilityScorecard(SerializableModel):
    scorecard_id: str
    tenant_id: str
    job_id: str
    contracted_revenue: float
    estimated_cost: float
    actual_cost: float
    estimated_gross_profit: float
    actual_gross_profit: float
    estimated_margin_percentage: float
    actual_margin_percentage: float
    cost_variance: float
    profitability_score: float
    margin_variance: MarginVariance | None
    cost_overrun_alert: CostOverrunAlert | None
    financial_hash: str


@dataclass(frozen=True)
class CashFlowWindow(SerializableModel):
    days: int
    through_date: str
    receivables: float
    payables: float
    net_cash_flow: float
    cumulative_net_cash_flow: float


@dataclass(frozen=True)
class CashFlowForecast(SerializableModel):
    forecast_id: str
    tenant_id: str
    as_of_date: str
    windows: tuple[CashFlowWindow, ...]
    overdue_receivables: float
    overdue_payables: float
    forecast_hash: str
