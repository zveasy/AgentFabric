# Worker Failure Runbook

1. Check `/health/workers` for stale heartbeats.
2. Inspect `/runtime/jobs` for running or assigned jobs.
3. Restart the worker deployment.
4. Retry failed jobs only after checking tenant quota and job payload safety.
5. Move unrecoverable jobs to dead-letter and notify tenant owner.

Never requeue dead-letter jobs without `runtime.jobs.manage` permission.
