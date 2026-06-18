"""Observability and reliability production helpers."""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agentfabric.phase1.observability import MetricsCollector


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class PrometheusExporter:
    """Converts in-process metrics snapshots into Prometheus text format."""

    def export(self, metrics: MetricsCollector) -> str:
        snapshot = metrics.snapshot()
        lines: list[str] = []
        for key, value in sorted(snapshot["counters"].items()):
            name = key.replace(".", "_")
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {value}")
        for key, series in sorted(snapshot["latencies_seconds"].items()):
            base = key.replace(".", "_")
            for idx, sample in enumerate(series):
                lines.append(f"{base}_sample{{index=\"{idx}\"}} {sample}")
        return "\n".join(lines) + ("\n" if lines else "")


class TraceExporter:
    """Writes trace spans/events as JSON lines to durable storage."""

    def __init__(self, output_file: str = "traces.jsonl") -> None:
        self.output_file = Path(output_file)

    def emit(self, trace: dict[str, Any]) -> None:
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        with self.output_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(trace, sort_keys=True) + "\n")


class BackupManager:
    """Backup/restore utility with timestamped snapshots."""

    def __init__(self, db_path: str, backup_dir: str = "backups") -> None:
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self) -> str:
        timestamp = utc_now_iso().replace(":", "-")
        target = self.backup_dir / f"agentfabric_{timestamp}.db"
        shutil.copy2(self.db_path, target)
        return str(target)

    def restore_backup(self, backup_file: str) -> None:
        source = Path(backup_file)
        if not source.exists():
            raise FileNotFoundError(f"backup not found: {backup_file}")
        shutil.copy2(source, self.db_path)


@dataclass
class RetryTask:
    task_id: str
    action: Callable[[], Any]
    max_attempts: int = 3
    base_delay_seconds: float = 0.05
    attempts: int = 0
    last_error: str | None = None


@dataclass
class RetryWorker:
    """Simple retry queue for transient failures with backoff."""

    tasks: list[RetryTask] = field(default_factory=list)

    def submit(self, task: RetryTask) -> None:
        self.tasks.append(task)

    def run_once(self) -> dict[str, list[str]]:
        completed: list[str] = []
        failed: list[str] = []
        remaining: list[RetryTask] = []
        for task in self.tasks:
            success = False
            while task.attempts < task.max_attempts:
                task.attempts += 1
                try:
                    task.action()
                    success = True
                    completed.append(task.task_id)
                    break
                except Exception as exc:  # pragma: no cover - resilience fallback
                    task.last_error = str(exc)
                    time.sleep(task.base_delay_seconds * task.attempts)
            if not success:
                failed.append(task.task_id)
                remaining.append(task)
        self.tasks = remaining
        return {"completed": completed, "failed": failed}
