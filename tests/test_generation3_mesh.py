from __future__ import annotations

from time import sleep
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agentfabric.collaboration import ContextStore, MeshWorkflowEngine, SharedMemory, TaskGraph, TaskNode
from agentfabric.errors import AuthorizationError, ConflictError
from agentfabric.events import EventStore
from agentfabric.identity import AgentCertificate, AgentIdentity, AgentPassport
from agentfabric.mesh import AgentDirectory, AgentDiscovery, MeshMessage, MessageBus, MessageType
from agentfabric.reputation import ReputationService
from agentfabric.server.app import create_app
from agentfabric.server.config import Settings
from veil_client import (
    AuditEventRequest,
    AuditEventResponse,
    PolicyCheckRequest,
    PolicyCheckResponse,
    SanitizeContextRequest,
    SanitizeContextResponse,
    TokenIssueRequest,
    TokenIssueResponse,
)


def passport(agent_id: str, name: str, capabilities: list[str], version: str = "1.0.0") -> AgentPassport:
    fingerprint = f"{agent_id}-fp"
    identity = AgentIdentity.create(
        agent_id=agent_id,
        name=name,
        version=version,
        owner="tests",
        organization="agentfabric",
        capabilities=capabilities,
        signing_fingerprint=fingerprint,
    )
    return AgentPassport(
        identity=identity,
        certificate=AgentCertificate.issue(agent_id=agent_id, signing_fingerprint=fingerprint),
    )


class TrackingVeilClient:
    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.calls: list[str] = []

    def sanitize_context(self, request: SanitizeContextRequest) -> SanitizeContextResponse:
        self.calls.append("sanitize_context")
        sanitized = {key: value for key, value in request.context.items() if key != "secret"}
        return SanitizeContextResponse(sanitized_context=sanitized, redactions=("secret",))

    def check_policy(self, request: PolicyCheckRequest) -> PolicyCheckResponse:
        self.calls.append("check_policy")
        return PolicyCheckResponse(allowed=self.allowed, reason="" if self.allowed else "blocked")

    def create_audit_event(self, request: AuditEventRequest) -> AuditEventResponse:
        self.calls.append("create_audit_event")
        return AuditEventResponse(event_id=f"audit:{request.agent_id}:{request.event_type}", accepted=True)

    def issue_agent_token(self, request: TokenIssueRequest) -> TokenIssueResponse:
        self.calls.append("issue_agent_token")
        return TokenIssueResponse(token=f"token:{request.agent_id}", expires_in_seconds=request.ttl_seconds)


class Generation3MeshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = AgentDirectory()
        self.directory.register(passport("planner", "PlannerAgent", ["planning"]))
        self.directory.register(passport("research", "ResearchAgent", ["research", "retrieval"]))
        self.directory.register(passport("web", "WebAgent", ["research"], version="1.2.0"))
        self.directory.register(passport("docs", "DocumentAgent", ["research", "analysis"]))
        self.directory.register(passport("code", "CodeAgent", ["coding", "execution"]))

    def test_capability_discovery_filters_version_and_health(self) -> None:
        self.directory.update_health("docs", "degraded")
        discovery = AgentDiscovery(self.directory)

        names = [item["identity"]["name"] for item in discovery.discover(capability="research")]
        self.assertEqual(names, ["ResearchAgent", "WebAgent"])

        versioned = discovery.discover(capability="research", version="1.x")
        self.assertEqual({item["identity"]["agent_id"] for item in versioned}, {"research", "web"})

        including_unhealthy = discovery.discover(capability="research", healthy_only=False)
        self.assertIn("docs", {item["identity"]["agent_id"] for item in including_unhealthy})

    def test_message_routing_uses_veil_boundary_and_audit_metadata(self) -> None:
        veil = TrackingVeilClient()
        bus = MessageBus(directory=self.directory, veil_client=veil, tenant_id="tenant-a")
        sent = bus.send(
            MeshMessage(
                source_agent="planner",
                destination_agent="research",
                payload={"query": "agent mesh", "secret": "redact-me"},
                message_type=MessageType.REQUEST.value,
            )
        )

        self.assertEqual(sent.payload, {"query": "agent mesh"})
        self.assertTrue(sent.signature)
        self.assertEqual(sent.trust_metadata["veil_redactions"], ["secret"])
        self.assertEqual(sent.trust_metadata["veil_audit_event_id"], "audit:planner:mesh.exchange")
        self.assertEqual(
            veil.calls,
            ["check_policy", "sanitize_context", "issue_agent_token", "create_audit_event"],
        )

    def test_policy_denial_blocks_message_without_agentfabric_trust_logic(self) -> None:
        bus = MessageBus(directory=self.directory, veil_client=TrackingVeilClient(allowed=False))
        with self.assertRaises(AuthorizationError):
            bus.send(MeshMessage(source_agent="planner", destination_agent="research", payload={}))

    def test_publish_subscribe_and_broadcast(self) -> None:
        bus = MessageBus(directory=self.directory, veil_client=TrackingVeilClient())
        received: list[MeshMessage] = []
        bus.subscribe("topic:updates", received.append)
        bus.publish("topic:updates", MeshMessage(source_agent="planner", destination_agent=None, payload={"x": 1}))
        broadcast = bus.broadcast(MeshMessage(source_agent="planner", destination_agent=None, payload={"all": True}))

        self.assertEqual(len(received), 1)
        self.assertEqual(len(broadcast), 4)

    def test_workflow_retries_checkpoints_reputation_and_recovery(self) -> None:
        context_store = ContextStore()
        event_store = EventStore()
        reputation = ReputationService()
        engine = MeshWorkflowEngine(
            context_store=context_store,
            event_store=event_store,
            reputation=reputation,
        )
        attempts = {"code": 0}
        graph = TaskGraph.from_dicts(
            "wf-1",
            [
                {"node_id": "research", "agent_id": "research", "capability": "research"},
                {
                    "node_id": "code",
                    "agent_id": "code",
                    "capability": "coding",
                    "dependencies": ["research"],
                    "max_retries": 1,
                },
            ],
        )

        def runner(node: TaskNode, payload: dict[str, object]) -> dict[str, object]:
            if node.node_id == "code":
                attempts["code"] += 1
                if attempts["code"] == 1:
                    raise RuntimeError("transient")
            return {"node": node.node_id, "deps": payload["dependency_results"]}

        result = engine.start(task_graph=graph, initial_payload={"goal": "build"}, node_runner=runner)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(attempts["code"], 2)
        self.assertTrue(result["checkpoints"])
        self.assertGreater(reputation.get("code").failures, 0)
        self.assertGreater(reputation.get("code").successful_tasks, 0)
        restored = engine.recover_from_checkpoint("wf-1", result["checkpoints"][0])
        self.assertEqual(restored["workflow_id"], "wf-1")
        self.assertGreaterEqual(len(event_store.replay("wf-1")), 3)

    def test_workflow_human_approval_and_failure(self) -> None:
        engine = MeshWorkflowEngine()
        approval_graph = TaskGraph.from_dicts(
            "wf-approval",
            [{"node_id": "review", "agent_id": "reviewer", "requires_human_approval": True}],
        )
        paused = engine.start(
            task_graph=approval_graph,
            initial_payload={},
            node_runner=lambda node, payload: {"ok": True},
        )
        self.assertEqual(paused["status"], "awaiting_approval")

        failing_graph = TaskGraph.from_dicts("wf-fail", [{"node_id": "bad", "agent_id": "bad"}])
        with self.assertRaises(ConflictError):
            engine.start(
                task_graph=failing_graph,
                initial_payload={},
                node_runner=lambda node, payload: (_ for _ in ()).throw(RuntimeError("boom")),
            )

    def test_shared_memory_does_not_expose_private_agent_memory(self) -> None:
        shared = SharedMemory()
        shared.write_artifact(workflow_id="wf", agent_id="research", key="summary", value={"text": "ok"})
        artifacts = shared.read_artifacts(workflow_id="wf")
        self.assertEqual(artifacts, {"research:summary": {"text": "ok"}})

    def test_parallel_execution(self) -> None:
        engine = MeshWorkflowEngine()
        graph = TaskGraph.from_dicts(
            "wf-parallel",
            [
                {"node_id": "a", "agent_id": "research"},
                {"node_id": "b", "agent_id": "web"},
                {"node_id": "join", "agent_id": "planner", "dependencies": ["a", "b"]},
            ],
        )

        def runner(node: TaskNode, payload: dict[str, object]) -> dict[str, object]:
            if node.node_id in {"a", "b"}:
                sleep(0.05)
            return {"node": node.node_id}

        result = engine.start(task_graph=graph, initial_payload={}, node_runner=runner)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(set(result["node_results"]), {"a", "b", "join"})


class Generation3ApiTests(unittest.TestCase):
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
            json={"principal_id": "dev", "tenant_id": "dev", "role": "developer", "scopes": []},
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

    def test_mesh_agents_workflow_and_reputation_apis(self) -> None:
        agents = self.client.get("/agents", params={"capability": "research"}, headers=self.headers)
        self.assertEqual(agents.status_code, 200)
        names = {item["identity"]["name"] for item in agents.json()["items"]}
        self.assertIn("ResearchAgent", names)
        self.assertIn("WebAgent", names)
        self.assertIn("DocumentAgent", names)

        sent = self.client.post(
            "/mesh/send",
            json={
                "source_agent": "planner-agent",
                "destination_agent": "research-agent",
                "payload": {"query": "mesh"},
            },
            headers=self.headers,
        )
        self.assertEqual(sent.status_code, 200)
        self.assertEqual(sent.json()["trust_metadata"]["veil_audit_accepted"], True)

        workflow = self.client.post(
            "/workflow/start",
            json={
                "workflow_id": "api-wf",
                "initial_payload": {"goal": "ship"},
                "nodes": [
                    {"node_id": "plan", "agent_id": "planner-agent"},
                    {"node_id": "research", "capability": "research", "dependencies": ["plan"]},
                    {"node_id": "review", "capability": "review", "dependencies": ["research"]},
                ],
            },
            headers=self.headers,
        )
        self.assertEqual(workflow.status_code, 200)
        self.assertEqual(workflow.json()["status"], "completed")

        fetched = self.client.get("/workflow/api-wf", headers=self.headers)
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["workflow_id"], "api-wf")

        reputation = self.client.get("/agents/research-agent/reputation", headers=self.headers)
        self.assertEqual(reputation.status_code, 200)
        self.assertGreater(reputation.json()["successful_tasks"], 0)


if __name__ == "__main__":
    unittest.main()
