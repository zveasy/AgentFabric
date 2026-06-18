"""Core runtime orchestrator lifecycle implementation."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from agentfabric.errors import ConflictError, NotFoundError
from agentfabric.phase1.manifest import AgentManifest, ManifestLoader
from agentfabric.phase1.memory import ScopedMemoryStore
from agentfabric.phase1.observability import MetricsCollector, StructuredLogger, Tracer
from agentfabric.phase1.protocol import ProtocolEnvelope
from agentfabric.phase1.sandbox import Sandbox, SandboxPolicy
from agentfabric.phase1.sdk import Agent, AgentExecutionContext
from agentfabric.phase1.security import PackageIntegrityVerifier, RuntimeSecrets
from agentfabric.phase1.tools import ToolRouter


@dataclass
class InstalledAgent:
    manifest: AgentManifest
    package_digest: str
    state: str
    factory: Callable[[], Agent]


class CancellationToken:
    """Run cancellation handle."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def cancelled(self) -> bool:
        return self._event.is_set()


class AgentOrchestrator:
    """Implements install -> load -> run -> suspend -> uninstall lifecycle."""

    def __init__(
        self,
        *,
        tool_router: ToolRouter | None = None,
        memory_store: ScopedMemoryStore | None = None,
        logger: StructuredLogger | None = None,
        metrics: MetricsCollector | None = None,
        integrity_verifier: PackageIntegrityVerifier | None = None,
        runtime_secrets: RuntimeSecrets | None = None,
        manifest_loader: ManifestLoader | None = None,
    ) -> None:
        self.tool_router = tool_router or ToolRouter()
        self.memory_store = memory_store or ScopedMemoryStore()
        self.logger = logger or StructuredLogger()
        self.metrics = metrics or MetricsCollector()
        self.tracer = Tracer(self.logger, self.metrics)
        self.integrity_verifier = integrity_verifier or PackageIntegrityVerifier()
        self.runtime_secrets = runtime_secrets or RuntimeSecrets()
        self.manifest_loader = manifest_loader or ManifestLoader()
        self._agents: dict[str, InstalledAgent] = {}

    def install(
        self,
        *,
        manifest_payload: dict[str, Any],
        package_payload: bytes,
        signature: str,
        signer_id: str,
        factory: Callable[[], Agent],
    ) -> AgentManifest:
        manifest = self.manifest_loader.from_dict(manifest_payload)
        digest = self.integrity_verifier.verify(signer_id, package_payload, signature)
        self._agents[manifest.agent_id] = InstalledAgent(
            manifest=manifest,
            package_digest=digest,
            state="installed",
            factory=factory,
        )
        self.metrics.inc("runtime.install.count")
        self.logger.log("INFO", "runtime.install", agent_id=manifest.agent_id, package_digest=digest)
        return manifest

    def load(self, agent_id: str) -> None:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise NotFoundError("agent is not installed")
        agent.state = "loaded"
        self.metrics.inc("runtime.load.count")
        self.logger.log("INFO", "runtime.load", agent_id=agent_id)

    def suspend(self, agent_id: str) -> None:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise NotFoundError("agent is not installed")
        agent.state = "suspended"
        self.metrics.inc("runtime.suspend.count")
        self.logger.log("INFO", "runtime.suspend", agent_id=agent_id)

    def uninstall(self, agent_id: str) -> None:
        if agent_id not in self._agents:
            raise NotFoundError("agent is not installed")
        del self._agents[agent_id]
        self.metrics.inc("runtime.uninstall.count")
        self.logger.log("INFO", "runtime.uninstall", agent_id=agent_id)

    def list_agents(self) -> list[dict[str, str]]:
        return [
            {
                "agent_id": item.manifest.agent_id,
                "version": item.manifest.version,
                "state": item.state,
            }
            for item in self._agents.values()
        ]

    def capabilities(self, agent_id: str) -> ProtocolEnvelope:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise NotFoundError("agent is not installed")
        return ProtocolEnvelope.build(
            "capability_discovery",
            {
                "agent_id": agent.manifest.agent_id,
                "capabilities": list(agent.manifest.capabilities),
                "permissions": list(agent.manifest.permissions),
            },
        )

    def run(
        self,
        *,
        agent_id: str,
        request: dict[str, Any],
        user_id: str,
        session_id: str,
        timeout_seconds: float | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> ProtocolEnvelope:
        installed = self._agents.get(agent_id)
        if installed is None:
            raise NotFoundError("agent is not installed")
        if installed.state == "suspended":
            raise ConflictError("agent is suspended")
        if installed.state == "installed":
            self.load(agent_id)

        cancellation_token = cancellation_token or CancellationToken()
        correlation_id = str(uuid4())
        sandbox_policy = SandboxPolicy(
            allow_network=bool(installed.manifest.sandbox.get("allow_network", False)),
            allowed_filesystem_paths=tuple(installed.manifest.sandbox.get("allowed_filesystem_paths", [])),
        )
        context = AgentExecutionContext(
            correlation_id=correlation_id,
            agent_id=installed.manifest.agent_id,
            user_id=user_id,
            session_id=session_id,
            tool_router=self.tool_router,
            manifest=installed.manifest,
            memory_store=self.memory_store,
            sandbox=Sandbox(sandbox_policy),
            max_tool_calls=installed.manifest.max_tool_calls,
            cancellation_check=cancellation_token.cancelled,
        )

        agent = installed.factory()
        effective_timeout = timeout_seconds or installed.manifest.max_run_seconds
        effective_timeout = min(effective_timeout, installed.manifest.max_run_seconds)
        started = monotonic()
        with self.tracer.span(correlation_id, "agent_run"):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(agent.run, request, context)
                try:
                    result_payload = future.result(timeout=effective_timeout)
                except FutureTimeout as exc:
                    cancellation_token.cancel()
                    self.metrics.inc("runtime.run.timeout.count")
                    self.logger.log(
                        "ERROR",
                        "runtime.run.timeout",
                        agent_id=agent_id,
                        correlation_id=correlation_id,
                        timeout_seconds=effective_timeout,
                    )
                    raise ConflictError("run timeout exceeded") from exc

        duration = monotonic() - started
        self.metrics.inc("runtime.run.count")
        self.metrics.observe_latency("runtime.run.seconds", duration)
        self.logger.log(
            "INFO",
            "runtime.run",
            agent_id=agent_id,
            correlation_id=correlation_id,
            duration_seconds=round(duration, 6),
        )
        return ProtocolEnvelope(
            protocol_version="v1",
            message_type="response",
            correlation_id=correlation_id,
            payload={
                "agent_id": agent_id,
                "result": result_payload,
                "events": context.events(),
            },
        )
