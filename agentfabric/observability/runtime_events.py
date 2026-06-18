"""Runtime event names."""

RUNTIME_EVENT_TYPES = {
    "runtime.job.created",
    "runtime.job.assigned",
    "runtime.job.started",
    "runtime.job.completed",
    "runtime.job.failed",
    "runtime.job.cancelled",
    "runtime.job.retried",
    "runtime.job.dead_lettered",
    "runtime.worker.registered",
    "runtime.worker.heartbeat_missed",
    "runtime.schedule.created",
    "runtime.schedule.triggered",
    "runtime.schedule.disabled",
    "runtime.schedule.enabled",
    "runtime.health.degraded",
    "runtime.health.recovered",
}
