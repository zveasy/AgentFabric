from __future__ import annotations

from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.collaboration import ContextStore, MeshWorkflowEngine, TaskGraph, TaskNode
from agentfabric.events import EventStore
from agentfabric.memory import DurableMemoryStore, MemoryPolicy, MemoryRecord
from agentfabric.migrations import Migration, MigrationRunner
from agentfabric.persistence import JsonPersistenceStore, MemoryPersistenceStore, SQLitePersistenceStore, UnitOfWork
from agentfabric.recovery import ReplayRecoveryEngine
from agentfabric.reputation import ReputationService
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings


class Generation4PersistenceTests(unittest.TestCase):
    def test_memory_json_and_sqlite_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stores = [
                MemoryPersistenceStore(),
                JsonPersistenceStore(Path(tmp) / "state.json"),
                SQLitePersistenceStore(Path(tmp) / "state.db"),
            ]
            for store in stores:
                store.initialize()
                store.put("agents", "a1", {"agent_id": "a1", "name": "Agent"})
                self.assertEqual(store.get("agents", "a1")["name"], "Agent")
                self.assertEqual(store.keys("agents"), ["a1"])
                self.assertEqual(store.health()["status"], "ok")
                self.assertTrue(store.delete("agents", "a1"))

    def test_unit_of_work_rolls_back_memory_and_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for store in [MemoryPersistenceStore(), SQLitePersistenceStore(Path(tmp) / "uow.db")]:
                store.initialize()
                with self.assertRaises(RuntimeError):
                    with UnitOfWork(store) as uow:
                        uow.put("events", "e1", {"event_id": "e1"})
                        raise RuntimeError("fail")
                self.assertIsNone(store.get("events", "e1"))

    def test_migration_ordering_idempotency_and_dry_run(self) -> None:
        store = MemoryPersistenceStore()
        calls: list[int] = []

        def apply_one(target: MemoryPersistenceStore) -> None:
            calls.append(1)
            target.put("x", "one", {"ok": True})

        def apply_two(target: MemoryPersistenceStore) -> None:
            calls.append(2)
            target.put("x", "two", {"ok": True})

        migrations = [
            Migration(version=2, name="two", apply=apply_two),
            Migration(version=1, name="one", apply=apply_one),
        ]
        runner = MigrationRunner(store, migrations)
        dry_run = runner.apply(dry_run=True)
        self.assertEqual(dry_run["current_version"], 0)

        first = runner.apply()
        second = runner.apply()
        self.assertEqual(calls, [1, 2])
        self.assertEqual(first["current_version"], 2)
        self.assertEqual(second["applied"], [])

    def test_migration_failure_fails_closed(self) -> None:
        store = MemoryPersistenceStore()

        def broken(_: MemoryPersistenceStore) -> None:
            raise ValueError("boom")

        runner = MigrationRunner(store, [Migration(version=1, name="broken", apply=broken)])
        with self.assertRaises(RuntimeError):
            runner.apply()
        self.assertEqual(runner.version_store.current_version(), 0)


class Generation4EventRecoveryTests(unittest.TestCase):
    def test_event_append_replay_restart_and_hash_chain_validation(self) -> None:
        store = MemoryPersistenceStore()
        events = EventStore(persistence=store)
        first = events.append("workflow.started", "wf", {"status": "started"})
        second = events.append("task.completed", "wf", {"node_id": "a", "agent_id": "agent", "latency_ms": 1})

        self.assertEqual(first.sequence, 1)
        self.assertEqual(second.previous_hash, first.event_hash)
        self.assertTrue(events.validate_integrity())

        restarted = EventStore(persistence=store)
        self.assertEqual([event.sequence for event in restarted.replay("wf")], [1, 2])

        corrupt = second.as_dict()
        corrupt["previous_hash"] = "bad"
        store.put("events", second.event_id, corrupt)
        self.assertFalse(EventStore(persistence=store).validate_integrity())

    def test_workflow_checkpoint_restore_and_restart_recovery(self) -> None:
        store = MemoryPersistenceStore()
        event_store = EventStore(persistence=store)
        context_store = ContextStore(persistence=store)
        engine = MeshWorkflowEngine(context_store=context_store, event_store=event_store)
        graph = TaskGraph.from_dicts(
            "wf-recover",
            [
                {"node_id": "research", "agent_id": "research"},
                {"node_id": "code", "agent_id": "code", "dependencies": ["research"]},
            ],
        )

        def runner(node: TaskNode, payload: dict[str, object]) -> dict[str, object]:
            return {"node": node.node_id, "deps": payload["dependency_results"]}

        result = engine.start(task_graph=graph, initial_payload={"goal": "recover"}, node_runner=runner)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(store.keys("checkpoints"))

        restarted_events = EventStore(persistence=store)
        recovered = ReplayRecoveryEngine(event_store=restarted_events, persistence=store).recover_workflow("wf-recover")
        self.assertEqual(recovered["status"], "completed")
        self.assertEqual(recovered["skip_completed_task_ids"], ["code", "research"])
        self.assertIn("latest_checkpoint", recovered)

    def test_recovery_fails_closed_on_corrupt_events(self) -> None:
        store = MemoryPersistenceStore()
        event_store = EventStore(persistence=store)
        event = event_store.append("workflow.started", "wf-bad", {"status": "started"})
        bad = event.as_dict()
        bad["event_hash"] = "corrupt"
        store.put("events", event.event_id, bad)
        with self.assertRaises(RuntimeError):
            ReplayRecoveryEngine(event_store=EventStore(persistence=store), persistence=store).recover_workflow("wf-bad")

    def test_reputation_reconstructs_from_events(self) -> None:
        event_store = EventStore()
        event_store.append("task.completed", "wf", {"agent_id": "agent", "node_id": "a", "latency_ms": 5})
        event_store.append("task.failed", "wf", {"agent_id": "agent", "node_id": "b", "latency_ms": 3})
        reputation = ReputationService(MemoryPersistenceStore())
        reputation.reconstruct_from_events(event_store)
        record = reputation.get("agent")
        self.assertEqual(record.successful_tasks, 1)
        self.assertEqual(record.failures, 1)


class Generation4MemoryTests(unittest.TestCase):
    def test_memory_retention_deletion_tenant_isolation_and_veil_boundary(self) -> None:
        store = MemoryPersistenceStore()
        memory = DurableMemoryStore(store, MemoryPolicy(short_term_ttl_days=1))
        created = memory.create(
            owner_agent_id="agent",
            tenant_id="tenant-a",
            source_workflow_id="wf",
            classification="internal",
            content={"summary": "safe"},
            veil_token_refs=("veil-ref-1",),
        )
        self.assertEqual(len(memory.list_for_agent(tenant_id="tenant-a", owner_agent_id="agent")), 1)
        self.assertEqual(memory.list_for_agent(tenant_id="tenant-b", owner_agent_id="agent"), [])

        with self.assertRaises(ValueError):
            memory.create(owner_agent_id="agent", tenant_id="tenant-a", content={"secret": "raw"})

        old = MemoryRecord(
            owner_agent_id="agent",
            tenant_id="tenant-a",
            source_workflow_id=None,
            classification="internal",
            content={"summary": "old"},
            created_at=datetime.now(tz=timezone.utc) - timedelta(days=3),
        )
        memory.put(old)
        self.assertEqual(memory.enforce_retention(), 1)
        self.assertTrue(memory.delete(tenant_id="tenant-a", owner_agent_id="agent", memory_id=created.memory_id))


class Generation4ApiTests(unittest.TestCase):
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
                )
            )
        )
        register = self.client.post(
            "/auth/principals/register",
            json={"principal_id": "dev", "tenant_id": "tenant-a", "role": "developer", "scopes": []},
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        self.assertEqual(register.status_code, 200)
        token = self.client.post(
            "/auth/token/issue",
            json={"principal_id": "dev"},
            headers={"X-AgentFabric-Bootstrap-Token": "bootstrap-test-token"},
        )
        self.headers = {"Authorization": f"Bearer {token.json()['access_token']}"}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_generation4_apis_and_auth(self) -> None:
        unauth = self.client.get("/events")
        self.assertEqual(unauth.status_code, 401)

        health = self.client.get("/health/persistence", headers=self.headers)
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

        workflow = self.client.post(
            "/workflow/start",
            json={
                "workflow_id": "api-g4",
                "nodes": [{"node_id": "research", "capability": "research"}],
                "initial_payload": {"goal": "durable"},
            },
            headers=self.headers,
        )
        self.assertEqual(workflow.status_code, 200)

        events = self.client.get("/workflow/api-g4/events", headers=self.headers)
        self.assertEqual(events.status_code, 200)
        self.assertGreater(events.json()["total"], 0)
        event_id = events.json()["items"][0]["event_id"]
        self.assertEqual(self.client.get(f"/events/{event_id}", headers=self.headers).status_code, 200)

        recovered = self.client.post("/workflow/api-g4/recover", headers=self.headers)
        self.assertEqual(recovered.status_code, 200)
        self.assertEqual(recovered.json()["recovered"], True)

        created = self.client.post(
            "/memory/research-agent",
            json={"content": {"summary": "safe"}, "veil_token_refs": ["veil-token-ref"]},
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 200)
        memory_id = created.json()["memory_id"]
        listed = self.client.get("/memory/research-agent", headers=self.headers)
        self.assertEqual(listed.json()["total"], 1)
        deleted = self.client.delete(f"/memory/research-agent/{memory_id}", headers=self.headers)
        self.assertEqual(deleted.status_code, 200)


if __name__ == "__main__":
    unittest.main()
