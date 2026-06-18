# Agent Operational Intelligence

AgentFabric Generation 16 adds tenant-scoped operational intelligence for agent quality after release. It is separate from infrastructure observability under `agentfabric/observability/`.

## Health Model

Each metric write produces a durable health snapshot with five normalized dimensions:

| Dimension | Inputs |
| --- | --- |
| Quality | evaluation score and hallucination rate |
| Latency | request latency |
| Reliability | tool failures, retries, and explicit reliability |
| Cost | execution cost |
| Feedback | user ratings and correction frequency |

Health states are `healthy`, `warning`, `degraded`, and `critical`. The overall average and weakest dimension both affect the state so a severe failure cannot be hidden by strong unrelated metrics.

## Drift Detection

Drift compares a stable baseline window with current observations. Direction is metric-aware: lower latency and failure rates are better, while higher evaluation scores and ratings are better. Detected deterioration is stored as a `DriftEvent` with the baseline, current value, change ratio, severity, and timestamp.

## Anomaly Detection

Anomaly detection compares the newest observation with prior values using a deterministic deviation score. Harmful spikes in latency, cost, retries, failures, or hallucinations and harmful collapses in quality, ratings, or reliability produce durable `AnomalyRecord` entries.

## Degradation States

The degradation monitor classifies operational state as `none`, `minor`, `moderate`, `major`, or `critical`. Health status establishes the minimum degradation level and drift evidence may raise it.

Configured quality gates fail closed when degradation exceeds the allowed level. Marketplace publication is blocked when agent health is critical, degradation is major or critical, or the quality dimension falls below the required threshold.

## Recommendation Lifecycle

The recommendation engine emits one of:

* `retrain`
* `rollback`
* `publish`
* `archive`

Every recommendation includes rationale, evidence, confidence, expected impact, status, and approval identity. Approval requires the `recommendations:approve` scope and remains tenant-scoped.

## APIs

* `POST /observability/metrics`
* `GET /observability/metrics`
* `GET /agents/{agent_id}/health`
* `GET /agents/{agent_id}/health/history`
* `GET /agents/{agent_id}/drift`
* `GET /agents/{agent_id}/anomalies`
* `GET /agents/{agent_id}/recommendations`
* `POST /agents/{agent_id}/recommendations/{id}/approve`
* `POST /agents/{agent_id}/compare`

## Events and Reproducibility

Metric records, health changes, drift, anomalies, degradation, recommendations, and version comparisons emit hash-chain-compatible durable events. Audit bundles include all derived records and their source metrics remain tenant-scoped, allowing the operational result to be reproduced.

## RBAC Scopes

* `observability:read`
* `observability:write`
* `health:read`
* `drift:read`
* `anomaly:read`
* `recommendations:read`
* `recommendations:approve`
