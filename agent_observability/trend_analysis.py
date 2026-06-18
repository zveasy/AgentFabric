"""Time-window trend and percentile analysis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import ceil
from statistics import mean, pstdev

from .metrics import AgentMetric


WINDOWS = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
}


class TrendAnalyzer:
    def analyze(
        self,
        metrics: list[AgentMetric],
        *,
        period: str = "daily",
        moving_window: int = 3,
        now: datetime | None = None,
    ) -> dict[str, object]:
        if period not in WINDOWS:
            raise ValueError("period must be hourly, daily, or weekly")
        now = now or datetime.now(tz=timezone.utc)
        duration = WINDOWS[period]
        records = sorted((metric for metric in metrics if metric.timestamp >= now - duration), key=lambda item: item.timestamp)
        values = [metric.value for metric in records]
        rolling = [
            round(mean(values[max(0, index - moving_window + 1) : index + 1]), 4)
            for index in range(len(values))
        ]
        deviation = pstdev(values) if len(values) > 1 else 0.0
        confidence = min(0.99, len(values) / (len(values) + 3)) if values else 0.0
        return {
            "period": period,
            "count": len(values),
            "average": round(mean(values), 4) if values else None,
            "rolling_average": rolling,
            "p50": _percentile(values, 0.5),
            "p95": _percentile(values, 0.95),
            "confidence": round(confidence / (1 + deviation), 4),
        }


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 4)
