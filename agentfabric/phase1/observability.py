"""Structured logging, metrics, and optional tracing helpers."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Iterator


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class StructuredLogger:
    """Writes JSON log lines to memory and optional file output."""

    def __init__(self, output_file: str | None = None, min_level: str = "INFO") -> None:
        self._output_file = output_file
        self._min_level = min_level
        self._entries: list[dict[str, Any]] = []

    def log(self, level: str, event: str, **fields: Any) -> None:
        entry = {
            "timestamp": utc_now().isoformat(),
            "level": level,
            "event": event,
            **fields,
        }
        self._entries.append(entry)
        if self._output_file:
            with open(self._output_file, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")

    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)


@dataclass
class MetricsCollector:
    counters: dict[str, int] = field(default_factory=dict)
    latencies_seconds: dict[str, list[float]] = field(default_factory=dict)

    def inc(self, name: str, value: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + value

    def observe_latency(self, name: str, value: float) -> None:
        self.latencies_seconds.setdefault(name, []).append(value)

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": dict(self.counters),
            "latencies_seconds": {k: list(v) for k, v in self.latencies_seconds.items()},
        }


class Tracer:
    """No-op style tracer that records timing via logger/metrics."""

    def __init__(self, logger: StructuredLogger, metrics: MetricsCollector) -> None:
        self._logger = logger
        self._metrics = metrics

    @contextmanager
    def span(self, correlation_id: str, name: str) -> Iterator[None]:
        start = monotonic()
        self._logger.log("DEBUG", "trace.start", correlation_id=correlation_id, span=name)
        try:
            yield
        finally:
            duration = monotonic() - start
            self._metrics.observe_latency(f"trace.{name}.seconds", duration)
            self._logger.log(
                "DEBUG",
                "trace.end",
                correlation_id=correlation_id,
                span=name,
                duration_seconds=round(duration, 6),
            )
