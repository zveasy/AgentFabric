from __future__ import annotations

import os
import uuid
import unittest

from fastapi.testclient import TestClient

from agentfabric.server.app import create_app
from agentfabric.server.config import Settings


class ServerPostgresRedisIntegrationTests(unittest.TestCase):
    def test_postgres_redis_queue_roundtrip(self) -> None:
        db_url = os.getenv("AGENTFABRIC_IT_DB_URL")
        redis_url = os.getenv("AGENTFABRIC_IT_REDIS_URL")
        if not db_url or not redis_url:
            self.skipTest("integration env vars not set")

        principal_id = f"it-user-{uuid.uuid4().hex[:8]}"
        settings = Settings(
            database_url=db_url,
            redis_url=redis_url,
            jwt_secret="it-secret",
            bootstrap_token="it-bootstrap-token",
        )
        client = TestClient(create_app(settings))

        register = client.post(
            "/auth/principals/register",
            json={
                "principal_id": principal_id,
                "tenant_id": principal_id,
                "principal_type": "user",
                "scopes": ["queue.write", "queue.read"],
            },
            headers={"X-AgentFabric-Bootstrap-Token": "it-bootstrap-token"},
        )
        self.assertEqual(register.status_code, 200)

        token_resp = client.post(
            "/auth/token/issue",
            json={"principal_id": principal_id, "ttl_seconds": 3600},
            headers={"X-AgentFabric-Bootstrap-Token": "it-bootstrap-token"},
        )
        self.assertEqual(token_resp.status_code, 200)
        headers = {"Authorization": f"Bearer {token_resp.json()['access_token']}"}

        queue_name = f"it-jobs-{uuid.uuid4().hex[:8]}"
        enqueue = client.post(
            "/queue/enqueue",
            json={"queue_name": queue_name, "payload": {"kind": "it", "value": 1}},
            headers=headers,
        )
        self.assertEqual(enqueue.status_code, 200)

        dequeue = client.post("/queue/dequeue", params={"queue_name": queue_name}, headers=headers)
        self.assertEqual(dequeue.status_code, 200)
        self.assertEqual(dequeue.json()["payload"]["kind"], "it")
        self.assertEqual(dequeue.json()["status"], "done")


if __name__ == "__main__":
    unittest.main()
