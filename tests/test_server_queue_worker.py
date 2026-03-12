from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentfabric.server.config import Settings
from agentfabric.server.database import build_session_factory, run_migrations
from agentfabric.server.queue import InMemoryQueueBackend
from agentfabric.server.services import QueueService


class QueueReliabilityTests(unittest.TestCase):
    def test_retry_then_dlq_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "queue.db"
            settings = Settings(
                database_url=f"sqlite:///{db_path}",
                redis_url="redis://127.0.0.1:6399/9",
                jwt_secret="test-secret",
            )
            run_migrations(settings.database_url)
            session_factory, _ = build_session_factory(settings)
            backend = InMemoryQueueBackend()

            with session_factory() as db:
                service = QueueService(db, backend=backend)
                service.enqueue("jobs", {"kind": "demo", "value": 1})
                db.commit()

            with session_factory() as db:
                service = QueueService(db, backend=backend)
                first = service.dequeue("jobs")
                assert first is not None
                outcome = service.ack_failure(first, "boom-1", max_attempts=2)
                self.assertEqual(outcome["status"], "retried")
                db.commit()

            with session_factory() as db:
                service = QueueService(db, backend=backend)
                second = service.dequeue("jobs")
                assert second is not None
                outcome = service.ack_failure(second, "boom-2", max_attempts=2)
                self.assertEqual(outcome["status"], "dlq")
                db.commit()

            with session_factory() as db:
                service = QueueService(db, backend=backend)
                self.assertIsNone(service.dequeue("jobs"))
                dlq_item = service.dequeue("jobs.dlq")
                self.assertIsNotNone(dlq_item)
                if dlq_item is not None:
                    service.ack_success(dlq_item.message_id)
                db.commit()


if __name__ == "__main__":
    unittest.main()
