"""Queue worker process for background job execution."""

from __future__ import annotations

import json
import time
from typing import Callable

from agentfabric.server.config import Settings
from agentfabric.server.database import build_session_factory
from agentfabric.server.queue import InMemoryQueueBackend, RedisQueueBackend
from agentfabric.server.services import QueueService


def _backend(settings: Settings):
    try:
        return RedisQueueBackend(settings.redis_url)
    except Exception:
        return InMemoryQueueBackend()


def run_worker(
    *,
    settings: Settings,
    queue_name: str = "default",
    handlers: dict[str, Callable[[dict], None]] | None = None,
    poll_interval_seconds: float = 0.5,
) -> None:
    handlers = handlers or {}
    session_factory, _ = build_session_factory(settings)
    backend = _backend(settings)

    while True:
        with session_factory() as db:
            service = QueueService(db, backend=backend)
            item = service.dequeue(queue_name)
            if item is None:
                time.sleep(poll_interval_seconds)
                continue
            kind = str(item.payload.get("kind", "default"))
            handler = handlers.get(kind)
            if handler:
                handler(item.payload)
            else:
                # Default no-op handler with logging-friendly output.
                print(json.dumps({"worker": "noop", "queue": queue_name, "message_id": item.message_id, "payload": item.payload}))
