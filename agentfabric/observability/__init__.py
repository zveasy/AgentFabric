"""
Observability: logging, metrics, optional tracing.
"""

from agentfabric.observability.logging_config import configure_logging, get_logger, bind_correlation_id, clear_context
from agentfabric.observability.metrics import (
    record_run,
    record_tool_call,
    record_sandbox_event,
    inc_active_runs,
    dec_active_runs,
)

__all__ = [
    "configure_logging",
    "get_logger",
    "bind_correlation_id",
    "clear_context",
    "record_run",
    "record_tool_call",
    "record_sandbox_event",
    "inc_active_runs",
    "dec_active_runs",
]
