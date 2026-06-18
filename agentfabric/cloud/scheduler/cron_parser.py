"""Small cron-like schedule parser."""

from __future__ import annotations

from datetime import datetime, timedelta


class CronParser:
    def next_after(self, expression: str, after: datetime) -> datetime:
        if expression.startswith("every "):
            amount, unit = expression.split()[1:3]
            seconds = int(amount) * {"second": 1, "seconds": 1, "minute": 60, "minutes": 60, "hour": 3600, "hours": 3600}[unit]
            return after + timedelta(seconds=seconds)
        fields = expression.split()
        if len(fields) != 5:
            raise ValueError("cron expression must have five fields or use 'every N unit'")
        minute, hour, *_ = fields
        candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(60 * 24 * 366):
            if self._matches(minute, candidate.minute) and self._matches(hour, candidate.hour):
                return candidate
            candidate += timedelta(minutes=1)
        raise ValueError("could not find next cron run")

    def _matches(self, field: str, value: int) -> bool:
        if field == "*":
            return True
        if field.startswith("*/"):
            return value % int(field[2:]) == 0
        return int(field) == value
