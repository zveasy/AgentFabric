# Queue Backlog Runbook

1. Check `/health/queues` and runtime metrics.
2. Identify tenant/job type driving backlog.
3. Scale workers for the affected queue.
4. Check quota, VEIL latency, marketplace entitlement failures, and governance stalls.
5. Dead-letter poisoned jobs after retry exhaustion.

Do not bypass quota limits to drain backlog.
