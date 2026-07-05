# RenovationOS Job Profitability and Cash Flow

Generation R4 adds deterministic financial visibility to RenovationOS Operations Foundation. It tracks job costs, receivables, payables, margins, cost variance, and short-term cash flow without external accounting or AI providers.

## Architecture

- `agentfabric/verticals/renovation/finance/` owns typed actual-cost records.
- `agentfabric/verticals/renovation/invoicing/` owns customer invoices, vendor payables, and bounded payment application.
- `agentfabric/verticals/renovation/profitability/` owns margin analysis, cost-overrun alerts, scorecards, and cash-flow forecasts.
- `RenovationFoundationService` enforces tenant ownership, derives accepted job financial context, persists evidence, and emits durable events.

All currency values are rounded to two decimal places at calculation boundaries.

## Job Cost Model

Supported cost categories are:

- material;
- labor;
- subcontractor;
- fee;
- tax;
- overhead.

Material costs are quantity multiplied by unit cost. Labor costs are hours multiplied by hourly rate. Subcontractor and overhead records preserve vendor or allocation details. Negative costs and non-positive quantities fail closed.

## Profitability

Contracted revenue is:

```text
accepted proposal total + approved change order totals
```

Estimated job cost is:

```text
proposal material and labor subtotal + contingency
```

Actual cost is the sum of persisted job-cost records. The scorecard calculates:

- estimated and actual gross profit;
- estimated and actual gross-margin percentage;
- cost variance;
- margin compression;
- cost-overrun amount and percentage;
- deterministic profitability score;
- financial artifact hash.

Margin variance is emitted when actual margin is below estimated margin. A cost-overrun alert is emitted when actual costs exceed estimated costs.

## Invoices and Payables

Invoices track issue date, due date, subtotal, tax, total, payments, status, and outstanding balance. Vendor payables track vendor, due date, amount, payments, status, and outstanding balance.

Payments:

- must be positive;
- cannot exceed the outstanding balance;
- cannot be applied to a fully paid record;
- retain deterministic reference IDs;
- are tenant isolated and audit exported.

## Cash Flow

`GET /renovation/cash-flow/forecast?as_of=YYYY-MM-DD` produces fixed windows for 7, 14, 30, 60, and 90 days.

Each window reports:

- receivables due;
- payables due;
- net cash flow;
- cumulative net cash flow.

Overdue receivables and payables are reported separately. Forecasts use persisted outstanding balances and due dates only.

## APIs

| Method | Path | Required scope |
| --- | --- | --- |
| POST | `/renovation/jobs/{job_id}/costs` | `renovation.finance.write` |
| GET | `/renovation/jobs/{job_id}/profitability` | `renovation.profitability.read` |
| POST | `/renovation/invoices` | `renovation.invoicing.write` |
| POST | `/renovation/invoices/{invoice_id}/payment` | `renovation.invoicing.write` |
| GET | `/renovation/invoices/{invoice_id}` | `renovation.invoicing.read` |
| POST | `/renovation/payables` | `renovation.invoicing.write` |
| POST | `/renovation/payables/{payable_id}/payment` | `renovation.invoicing.write` |
| GET | `/renovation/cash-flow/forecast` | `renovation.cashflow.read` |
| GET | `/renovation/owner-summary` | `renovation.finance.read` |

Forecast and owner-summary endpoints require an `as_of` query parameter.

## Replay and Audit

Original cost, invoice, and payable inputs are persisted. Payment history is replayed in stored order. Scorecards store contracted revenue, estimated cost, actual-cost snapshots, and approved change-order IDs. Forecasts store exact invoice and payable snapshots.

Replay fails closed if regenerated artifacts differ.

Audit bundles include:

- job costs and typed cost details;
- invoices and payments;
- vendor payables;
- margin variance and cost-overrun records;
- profitability scorecards;
- cash-flow forecasts;
- owner summaries;
- deterministic financial hashes and input evidence.

## Marketplace

RenovationOS Operations Foundation version `4.0.0` added financial visibility, job profitability, cost-overrun detection, invoice and payable tracking, and cash-flow forecasting. Version `5.0.0` adds CRM and customer portal capabilities.
