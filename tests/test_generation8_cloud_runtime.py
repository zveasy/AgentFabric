from __future__ import annotations

from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.cloud import CloudRuntime, RuntimeConfig, RuntimeJob, Worker
from agentfabric.cloud.queue_backends import MemoryJobQueue, RedisJobQueue, SQLiteJobQueue
from agentfabric.cloud.scheduler import ScheduledJob, SchedulerService
from agentfabric.errors import AuthorizationError, ConflictError
from agentfabric.events import EventStore
from agentfabric.observability import DeploymentHealth, MetricsRegistry, TenantUsageMetrics
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.quotas import LimitEnforcer, QuotaPolicy, QuotaTracker
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings
from veil_client import MockVeilClient, PolicyCheckResponse


class DenyVeilClient(MockVeilClient):
    def check_policy(self, request):
        return PolicyCheckResponse(False, "denied")


class Generation8CloudRuntimeServiceTests(unittest.TestCase):
    def job(self, **extra) -> RuntimeJob:
        values = {
            "tenant_id": "tenant-a",
            "organization_id": "org-a",
            "created_by": "owner-a",
            "job_type": "agent_run",
            "payload": {"agent_id": "agent-a"},
            "max_attempts": 2,
        }
        values.update(extra)
        return RuntimeJob(**values)

    def test_memory_sqlite_and_redis_fallback_queues(self) -> None:
        memory = MemoryJobQueue()
        queued = memory.enqueue(self.job())
        self.assertEqual(memory.dequeue(tenant_id="tenant-a").job_id, queued.job_id)
        self.assertIsNone(memory.dequeue(tenant_id="tenant-b"))

        with tempfile.TemporaryDirectory() as tmp:
            sqlite = SQLiteJobQueue(Path(tmp) / "queue.db")
            sqlite_job = sqlite.enqueue(self.job(job_type="workflow_step"))
            self.assertEqual(SQLiteJobQueue(Path(tmp) / "queue.db").get(sqlite_job.job_id).job_type, "workflow_step")

        redis = RedisJobQueue("redis://127.0.0.1:1/0", fallback=True)
        self.assertIn(redis.health()["backend"], {"redis", "redis-fallback"})

    def test_worker_registration_heartbeat_dispatch_retry_cancel_and_dead_letter(self) -> None:
        store = MemoryPersistenceStore()
        events = EventStore(persistence=store)
        runtime = CloudRuntime(
            queue=MemoryJobQueue(),
            persistence=store,
            event_store=events,
            veil_client=MockVeilClient(),
            quota_enforcer=LimitEnforcer(QuotaTracker()),
            quota_policy=lambda _: QuotaPolicy(compute_seconds=10),
            config=RuntimeConfig(max_attempts=1),
        )
        worker = runtime.register_worker(Worker(tenant_id="tenant-a", worker_id="worker-a"))
        self.assertEqual(worker.worker_id, "worker-a")
        self.assertEqual(runtime.heartbeat("worker-a").status, "healthy")

        runtime.submit(self.job(job_type="workflow_step"))
        completed = runtime.dispatcher.dispatch_one(tenant_id="tenant-a", worker_id="worker-a")
        self.assertEqual(completed.status, "completed")

        cancelled_job = runtime.submit(self.job())
        self.assertEqual(runtime.cancel(cancelled_job.job_id).status, "cancelled")
        self.assertEqual(runtime.retry(cancelled_job.job_id).status, "queued")
        self.assertEqual(runtime.dispatcher.dispatch_one(tenant_id="tenant-a", worker_id="worker-a").status, "completed")

        failing = runtime.submit(self.job(payload={"agent_id": "agent-a", "force_fail": True}, max_attempts=1))
        dead = runtime.dispatcher.dispatch_one(tenant_id="tenant-a", worker_id="worker-a")
        self.assertEqual(dead.status, "dead_lettered")
        self.assertEqual(runtime.requeue_dead_letter(failing.job_id).status, "queued")
        self.assertTrue(any(event.event_type == "runtime.job.dead_lettered" for event in events.replay()))

    def test_scheduler_health_metrics_quota_governance_entitlement_and_veil_boundaries(self) -> None:
        store = MemoryPersistenceStore()
        events = EventStore(persistence=store)
        runtime = CloudRuntime(
            queue=MemoryJobQueue(),
            persistence=store,
            event_store=events,
            veil_client=MockVeilClient(),
            quota_enforcer=LimitEnforcer(QuotaTracker()),
            quota_policy=lambda _: QuotaPolicy(compute_seconds=10),
        )
        scheduler = SchedulerService(persistence=store, event_store=events, runtime=runtime)
        schedule = scheduler.create(
            ScheduledJob(
                tenant_id="tenant-a",
                organization_id="org-a",
                created_by="owner-a",
                job_type="recovery",
                payload={"workflow_id": "wf"},
                run_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1),
            )
        )
        triggered = scheduler.trigger_due("tenant-a")
        self.assertEqual(len(triggered), 1)
        self.assertFalse(scheduler.get(schedule.schedule_id).enabled)
        self.assertEqual(DeploymentHealth(persistence=store, runtime=runtime).ready()["status"], "ok")
        self.assertEqual(TenantUsageMetrics(runtime).snapshot("tenant-a")["jobs_total"], 1)
        self.assertIn("queued_jobs", MetricsRegistry().runtime_snapshot(runtime))

        runtime.dispatcher.governance_check = lambda job: (_ for _ in ()).throw(AuthorizationError("not approved"))
        with self.assertRaises(AuthorizationError):
            runtime.dispatcher.execute(self.job(job_type="governance_action", payload={"proposal_id": "p"}))

        runtime.dispatcher.entitlement_check = lambda job: (_ for _ in ()).throw(AuthorizationError("no entitlement"))
        with self.assertRaises(AuthorizationError):
            runtime.dispatcher.execute(self.job(payload={"package_id": "pkg"}))

        denied = CloudRuntime(queue=MemoryJobQueue(), persistence=store, event_store=events, veil_client=DenyVeilClient())
        with self.assertRaises(AuthorizationError):
            denied.dispatcher.execute(self.job())

        limited = CloudRuntime(
            queue=MemoryJobQueue(),
            persistence=store,
            event_store=events,
            veil_client=MockVeilClient(),
            quota_enforcer=LimitEnforcer(QuotaTracker()),
            quota_policy=lambda _: QuotaPolicy(compute_seconds=0),
        )
        with self.assertRaises(ConflictError):
            limited.dispatcher.execute(self.job())


class Generation8CloudRuntimeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "api.db"
        self.client = TestClient(
            create_app(
                Settings(
                    database_url=f"sqlite:///{db_path}",
                    production_db_path=str(Path(self.tmp.name) / "prod.db"),
                    redis_url="memory://",
                    jwt_secret="test-secret",
                    bootstrap_token="bootstrap-test-token",
                    cloud_queue_backend="memory",
                )
            )
        )
        register = self.client.post(
            "/auth/principals/register",
            json={"principal_id": "owner-a", "tenant_id": "tenant-a", "role": "owner", "scopes": []},
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        self.assertEqual(register.status_code, 200)
        token = self.client.post(
            "/auth/token/issue",
            json={"principal_id": "owner-a"},
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        self.headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
        tenant = self.client.post(
            "/tenants",
            json={"tenant_id": "tenant-a", "organization_id": "org-a", "name": "Tenant A", "billing_plan": "enterprise"},
            headers=self.headers,
        )
        self.assertEqual(tenant.status_code, 200)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_runtime_apis_health_metrics_rbac_and_events(self) -> None:
        worker = self.client.post("/runtime/workers/register", json={"worker_id": "worker-a"}, headers=self.headers)
        self.assertEqual(worker.status_code, 200)
        heartbeat = self.client.post("/runtime/workers/worker-a/heartbeat", headers=self.headers)
        self.assertEqual(heartbeat.json()["status"], "healthy")

        created = self.client.post(
            "/runtime/jobs",
            json={"job_type": "workflow_step", "payload": {"agent_id": "agent-a"}, "dispatch_now": True, "worker_id": "worker-a"},
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["status"], "completed")
        job_id = created.json()["job_id"]
        self.assertEqual(self.client.get(f"/runtime/jobs/{job_id}", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get("/runtime/jobs", headers=self.headers).json()["total"], 1)

        retry = self.client.post(f"/runtime/jobs/{job_id}/retry", headers=self.headers)
        self.assertEqual(retry.status_code, 200)
        cancel = self.client.post(f"/runtime/jobs/{job_id}/cancel", headers=self.headers)
        self.assertEqual(cancel.json()["status"], "cancelled")

        failing = self.client.post(
            "/runtime/jobs",
            json={"job_type": "agent_run", "payload": {"agent_id": "agent-a", "force_fail": True}, "max_attempts": 1, "dispatch_now": True},
            headers=self.headers,
        )
        self.assertEqual(failing.json()["status"], "dead_lettered")
        dead = self.client.get("/runtime/dead-letter", headers=self.headers)
        self.assertEqual(dead.json()["total"], 1)
        requeued = self.client.post(f"/runtime/dead-letter/{failing.json()['job_id']}/requeue", headers=self.headers)
        self.assertEqual(requeued.json()["status"], "queued")

        schedule = self.client.post(
            "/runtime/schedules",
            json={"job_type": "recovery", "payload": {"workflow_id": "wf"}, "run_at": datetime.now(tz=timezone.utc).isoformat()},
            headers=self.headers,
        )
        self.assertEqual(schedule.status_code, 200)
        schedule_id = schedule.json()["schedule_id"]
        self.assertEqual(self.client.post(f"/runtime/schedules/{schedule_id}/disable", headers=self.headers).json()["enabled"], False)
        self.assertEqual(self.client.post(f"/runtime/schedules/{schedule_id}/enable", headers=self.headers).json()["enabled"], True)

        self.assertEqual(self.client.get("/health/runtime", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get("/health/workers", headers=self.headers).json()["total"], 1)
        self.assertEqual(self.client.get("/health/queues", headers=self.headers).status_code, 200)
        metrics = self.client.get("/metrics/tenants/tenant-a", headers=self.headers)
        self.assertEqual(metrics.status_code, 200)
        self.assertGreaterEqual(metrics.json()["jobs_total"], 2)
        events = self.client.get("/events", headers=self.headers).json()["items"]
        self.assertTrue(any(event["event_type"] == "runtime.job.created" for event in events))
        self.assertEqual(self.client.get("/runtime/jobs").status_code, 401)

    def test_runtime_quota_and_sensitive_payload_safety(self) -> None:
        patched = self.client.patch("/tenants/tenant-a/quotas", json={"api_calls": 0}, headers=self.headers)
        self.assertEqual(patched.status_code, 200)
        blocked = self.client.post("/runtime/jobs", json={"job_type": "agent_run", "payload": {"agent_id": "agent-a"}}, headers=self.headers)
        self.assertEqual(blocked.status_code, 409)

        self.client.patch("/tenants/tenant-a/quotas", json={"api_calls": 10}, headers=self.headers)
        raw = self.client.post("/runtime/jobs", json={"job_type": "agent_run", "payload": {"secret": "raw-value"}}, headers=self.headers)
        self.assertEqual(raw.status_code, 400)


if __name__ == "__main__":
    unittest.main()
