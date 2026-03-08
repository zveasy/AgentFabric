from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from agentfabric.errors import AuthorizationError, ConflictError, ValidationError
from agentfabric.phase1.manifest import ManifestLoader
from agentfabric.phase1.memory import ScopedMemoryStore
from agentfabric.phase1.runtime import AgentOrchestrator, CancellationToken
from agentfabric.phase1.sdk import Agent


def manifest_payload(*, permissions: list[str] | None = None, max_tool_calls: int = 4, max_run_seconds: float = 1.0) -> dict:
    return {
        "manifest_version": "v1",
        "agent_id": "local.echo",
        "name": "Local Echo",
        "description": "Echoes and calls a tool",
        "version": "1.0.0",
        "entrypoint": "tests.test_phase1_runtime:EchoToolAgent",
        "capabilities": ["echo", "tool_use"],
        "permissions": ["tool.llm.invoke"] if permissions is None else permissions,
        "sandbox": {
            "allow_network": False,
            "allowed_filesystem_paths": [],
        },
        "max_tool_calls": max_tool_calls,
        "max_run_seconds": max_run_seconds,
    }


class EchoToolAgent(Agent):
    def run(self, request: dict, ctx) -> dict:
        result = ctx.call_tool("llm.mock", {"prompt": request["prompt"]})
        ctx.memory_set("last_prompt", request["prompt"], ttl_seconds=30)
        remembered = ctx.memory_get("last_prompt")
        ctx.emit_event("tool_call_completed", prompt=request["prompt"])
        return {"tool_text": result["text"], "remembered": remembered}


class LoopToolAgent(Agent):
    def run(self, request: dict, ctx) -> dict:
        for _ in range(10):
            ctx.call_tool("llm.mock", {"prompt": "x"})
        return {"ok": True}


class SleepAgent(Agent):
    def run(self, request: dict, ctx) -> dict:
        time.sleep(0.3)
        return {"done": True}


class SandboxEscapeAgent(Agent):
    def run(self, request: dict, ctx) -> dict:
        # These calls intentionally exercise sandbox-denied paths.
        ctx.sandbox.read_file("/etc/passwd")
        return {"unexpected": True}


class Phase1RuntimeTests(unittest.TestCase):
    def _make_runtime(self) -> AgentOrchestrator:
        tmp = tempfile.NamedTemporaryFile(prefix="agentfabric-memory-", delete=False)
        tmp.close()
        memory_path = Path(tmp.name)
        memory_path.write_text("{}", encoding="utf-8")
        runtime = AgentOrchestrator(memory_store=ScopedMemoryStore(storage_file=str(memory_path)))
        runtime.tool_router.register_tool("llm.mock", "tool.llm.invoke", lambda args: {"text": f"mock:{args['prompt']}"})
        runtime.integrity_verifier.register_signer_key("dev-signer", "k1")
        return runtime

    def test_manifest_validation(self) -> None:
        loader = ManifestLoader()
        with self.assertRaises(ValidationError):
            loader.from_dict({"manifest_version": "v1"})

    def test_lifecycle_install_load_run_suspend_uninstall(self) -> None:
        runtime = self._make_runtime()
        payload = b"package"
        signature = runtime.integrity_verifier.sign("dev-signer", payload)
        runtime.install(
            manifest_payload=manifest_payload(),
            package_payload=payload,
            signature=signature,
            signer_id="dev-signer",
            factory=EchoToolAgent,
        )
        runtime.load("local.echo")
        response = runtime.run(
            agent_id="local.echo",
            request={"prompt": "hello"},
            user_id="u1",
            session_id="s1",
        )
        self.assertEqual(response.message_type, "response")
        self.assertEqual(response.payload["result"]["tool_text"], "mock:hello")
        self.assertEqual(response.payload["result"]["remembered"], "hello")
        self.assertEqual(response.payload["events"][0]["event_name"], "tool_call_completed")
        runtime.suspend("local.echo")
        with self.assertRaises(ConflictError):
            runtime.run(agent_id="local.echo", request={"prompt": "blocked"}, user_id="u1", session_id="s1")
        runtime.uninstall("local.echo")
        self.assertEqual(runtime.list_agents(), [])

    def test_tool_permission_and_call_limit_enforced(self) -> None:
        runtime = self._make_runtime()
        payload = b"package"
        signature = runtime.integrity_verifier.sign("dev-signer", payload)
        runtime.install(
            manifest_payload=manifest_payload(permissions=[], max_tool_calls=2),
            package_payload=payload,
            signature=signature,
            signer_id="dev-signer",
            factory=EchoToolAgent,
        )
        with self.assertRaises(AuthorizationError):
            runtime.run(agent_id="local.echo", request={"prompt": "denied"}, user_id="u1", session_id="s1")

        runtime2 = self._make_runtime()
        signature2 = runtime2.integrity_verifier.sign("dev-signer", payload)
        runtime2.install(
            manifest_payload=manifest_payload(max_tool_calls=1),
            package_payload=payload,
            signature=signature2,
            signer_id="dev-signer",
            factory=LoopToolAgent,
        )
        with self.assertRaises(ConflictError):
            runtime2.run(agent_id="local.echo", request={"prompt": "x"}, user_id="u1", session_id="s1")

    def test_timeout_cancellation_and_sandbox_denial(self) -> None:
        runtime = self._make_runtime()
        payload = b"package"
        signature = runtime.integrity_verifier.sign("dev-signer", payload)
        runtime.install(
            manifest_payload=manifest_payload(max_run_seconds=0.1),
            package_payload=payload,
            signature=signature,
            signer_id="dev-signer",
            factory=SleepAgent,
        )
        token = CancellationToken()
        with self.assertRaises(ConflictError):
            runtime.run(
                agent_id="local.echo",
                request={"prompt": "slow"},
                user_id="u1",
                session_id="s1",
                cancellation_token=token,
            )
        self.assertTrue(token.cancelled())

        runtime2 = self._make_runtime()
        signature2 = runtime2.integrity_verifier.sign("dev-signer", payload)
        runtime2.install(
            manifest_payload=manifest_payload(),
            package_payload=payload,
            signature=signature2,
            signer_id="dev-signer",
            factory=SandboxEscapeAgent,
        )
        with self.assertRaises(AuthorizationError):
            runtime2.run(agent_id="local.echo", request={"prompt": "x"}, user_id="u1", session_id="s1")


if __name__ == "__main__":
    unittest.main()
