"""
Structured logging with correlation IDs. JSON output for production.
"""

from __future__ import annotations

import logging
import structlog


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    """Configure structlog with optional JSON output and correlation ID binding."""
    if json_logs:
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper(), logging.INFO)),
            context_class=dict,
            cache_logger_on_first_use=True,
        )
    else:
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper(), logging.INFO)),
            context_class=dict,
            cache_logger_on_first_use=True,
        )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    return structlog.get_logger(name)


def bind_correlation_id(correlation_id: str) -> None:
    """Set correlation_id in context for all subsequent log events in this context."""
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)


def clear_context() -> None:
    structlog.contextvars.clear_contextvars()
