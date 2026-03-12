"""
Prometheus-style metrics: run counts, latencies, tool calls, errors.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram, Gauge


# Run metrics
RUNS_TOTAL = Counter("agentfabric_runs_total", "Total agent runs", ["agent_id", "status"])
RUN_DURATION = Histogram("agentfabric_run_duration_seconds", "Run duration", ["agent_id"], buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0))
TOOL_CALLS_TOTAL = Counter("agentfabric_tool_calls_total", "Total tool calls", ["agent_id", "tool_name", "status"])
SANDBOX_EVENTS_TOTAL = Counter("agentfabric_sandbox_events_total", "Sandbox events", ["agent_id", "kind"])
ACTIVE_RUNS = Gauge("agentfabric_active_runs", "Currently active runs", ["agent_id"])


def record_run(agent_id: str, success: bool, duration_seconds: float) -> None:
    RUNS_TOTAL.labels(agent_id=agent_id, status="success" if success else "error").inc()
    RUN_DURATION.labels(agent_id=agent_id).observe(duration_seconds)


def record_tool_call(agent_id: str, tool_name: str, success: bool) -> None:
    TOOL_CALLS_TOTAL.labels(agent_id=agent_id, tool_name=tool_name, status="success" if success else "error").inc()


def record_sandbox_event(agent_id: str, kind: str) -> None:
    SANDBOX_EVENTS_TOTAL.labels(agent_id=agent_id, kind=kind).inc()


def inc_active_runs(agent_id: str) -> None:
    ACTIVE_RUNS.labels(agent_id=agent_id).inc()


def dec_active_runs(agent_id: str) -> None:
    ACTIVE_RUNS.labels(agent_id=agent_id).dec()
