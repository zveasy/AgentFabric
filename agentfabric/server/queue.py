"""Queue backends for async jobs."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentfabric.server.models import QueueMessage


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class QueueItem:
    message_id: str
    queue_name: str
    payload: dict[str, Any]
    attempts: int
    created_at: datetime


class QueueBackend:
    def enqueue(self, queue_name: str, payload: dict[str, Any]) -> QueueItem:
        raise NotImplementedError

    def dequeue(self, queue_name: str) -> QueueItem | None:
        raise NotImplementedError

    def healthcheck(self) -> bool:
        raise NotImplementedError


class RedisQueueBackend(QueueBackend):
    """Redis list-backed queue for multi-worker async processing."""

    def __init__(self, redis_url: str) -> None:
        self._client = Redis.from_url(redis_url, decode_responses=True)
        self._client.ping()

    def enqueue(self, queue_name: str, payload: dict[str, Any]) -> QueueItem:
        item = QueueItem(
            message_id=uuid4().hex,
            queue_name=queue_name,
            payload=payload,
            attempts=0,
            created_at=utc_now(),
        )
        self._client.lpush(queue_name, json.dumps({"message_id": item.message_id, "payload": payload, "created_at": item.created_at.isoformat()}))
        return item

    def dequeue(self, queue_name: str) -> QueueItem | None:
        raw = self._client.rpop(queue_name)
        if raw is None:
            return None
        data = json.loads(raw)
        return QueueItem(
            message_id=data["message_id"],
            queue_name=queue_name,
            payload=data["payload"],
            attempts=1,
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def healthcheck(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False


class InMemoryQueueBackend(QueueBackend):
    """Fallback queue backend for tests/local development."""

    def __init__(self) -> None:
        self._queues: dict[str, deque[QueueItem]] = {}

    def enqueue(self, queue_name: str, payload: dict[str, Any]) -> QueueItem:
        item = QueueItem(
            message_id=uuid4().hex,
            queue_name=queue_name,
            payload=payload,
            attempts=0,
            created_at=utc_now(),
        )
        self._queues.setdefault(queue_name, deque()).append(item)
        return item

    def dequeue(self, queue_name: str) -> QueueItem | None:
        queue = self._queues.setdefault(queue_name, deque())
        if not queue:
            return None
        item = queue.popleft()
        return QueueItem(
            message_id=item.message_id,
            queue_name=item.queue_name,
            payload=item.payload,
            attempts=item.attempts + 1,
            created_at=item.created_at,
        )

    def healthcheck(self) -> bool:
        return True


class SqlQueueStore:
    """Persistent queue metadata in Postgres."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def record_enqueue(self, queue_name: str, payload: dict[str, Any], message_id: str) -> QueueMessage:
        row = QueueMessage(
            message_id=message_id,
            queue_name=queue_name,
            payload_json=json.dumps(payload, sort_keys=True),
            status="queued",
            attempts=0,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def mark_processing(self, message_id: str) -> None:
        row = self.db.get(QueueMessage, message_id)
        if row:
            row.status = "processing"
            row.attempts += 1
            self.db.add(row)
            self.db.flush()

    def mark_done(self, message_id: str) -> None:
        row = self.db.get(QueueMessage, message_id)
        if row:
            row.status = "done"
            row.last_error = ""
            self.db.add(row)
            self.db.flush()

    def mark_failed(self, message_id: str, error: str) -> None:
        row = self.db.get(QueueMessage, message_id)
        if row:
            row.status = "failed"
            row.last_error = error
            self.db.add(row)
            self.db.flush()

    def get_attempts(self, message_id: str) -> int:
        row = self.db.get(QueueMessage, message_id)
        if row is None:
            return 0
        return int(row.attempts)

    def pending_messages(self, queue_name: str) -> list[QueueMessage]:
        rows = self.db.execute(
            select(QueueMessage).where(
                QueueMessage.queue_name == queue_name,
                QueueMessage.status == "queued",
            )
        ).scalars().all()
        return list(rows)

    def list_messages(self, queue_name: str, *, status: str | None = None, limit: int = 100) -> list[QueueMessage]:
        stmt = select(QueueMessage).where(QueueMessage.queue_name == queue_name)
        if status:
            stmt = stmt.where(QueueMessage.status == status)
        stmt = stmt.order_by(QueueMessage.created_at.desc()).limit(limit)
        rows = self.db.execute(stmt).scalars().all()
        return list(rows)
