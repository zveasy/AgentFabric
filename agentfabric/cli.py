"""CLI for operating AgentFabric phase 1-4 scaffolding."""

from __future__ import annotations

import argparse
import base64
import importlib
import json
from hashlib import sha256
from pathlib import Path
from typing import Callable
from typing import Any

from agentfabric.phase1.sdk import Agent
from agentfabric.phase2.models import MeterEvent, PackageUpload
from agentfabric.platform import AgentFabricPlatform

STATE_FILE = Path(".agentfabric_runtime_state.json")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentfabric")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed-dev", help="register developer signing secret")
    seed.add_argument("--developer", required=True)
    seed.add_argument("--secret", required=True)

    install = sub.add_parser("install", help="install a local runtime agent")
    install.add_argument("--manifest", required=True, help="path to manifest json")
    install.add_argument("--payload", required=True, help="package payload text")
    install.add_argument("--signer", required=True)
    install.add_argument("--key", required=True, help="signer key used for signature verification")
    install.add_argument("--signature", required=False, help="optional pre-computed signature")

    load = sub.add_parser("load", help="load an installed runtime agent")
    load.add_argument("--agent-id", required=True)

    run_agent = sub.add_parser("run", help="run a loaded runtime agent")
    run_agent.add_argument("--agent-id", required=True)
    run_agent.add_argument("--user", required=True)
    run_agent.add_argument("--session", required=True)
    run_agent.add_argument("--request", required=True, help="json request payload")

    suspend = sub.add_parser("suspend", help="suspend runtime agent")
    suspend.add_argument("--agent-id", required=True)

    uninstall = sub.add_parser("uninstall", help="uninstall runtime agent")
    uninstall.add_argument("--agent-id", required=True)

    runtime_list = sub.add_parser("agent-list", help="list runtime-installed agents")

    publish = sub.add_parser("publish", help="publish an agent package")
    publish.add_argument("--developer", required=True)
    publish.add_argument("--namespace", required=True)
    publish.add_argument("--package", required=True)
    publish.add_argument("--version", required=True)
    publish.add_argument("--category", required=True)
    publish.add_argument("--payload", required=True)
    publish.add_argument("--permissions", nargs="*", default=[])

    list_cmd = sub.add_parser("list", help="list packages")
    list_cmd.add_argument("--query")
    list_cmd.add_argument("--category")
    list_cmd.add_argument("--permissions", nargs="*", default=[])

    run = sub.add_parser("meter-run", help="enqueue and process run event")
    run.add_argument("--tenant", required=True)
    run.add_argument("--actor", required=True)
    run.add_argument("--fqid", required=True)
    run.add_argument("--idempotency-key", required=True)
    return parser


def _registry_manifest_for(package_name: str, permissions: list[str]) -> dict[str, Any]:
    return {
        "manifest_version": "v1",
        "name": package_name,
        "description": f"{package_name} package",
        "entrypoint": "agent.py:run",
        "permissions": permissions,
    }


class EchoAgent(Agent):
    """Fallback runtime agent used by quickstart CLI paths."""

    def run(self, request: dict[str, Any], ctx) -> dict[str, Any]:
        return {"echo": request}


def _factory_from_entrypoint(entrypoint: str) -> Callable[[], Agent]:
    module_name, symbol_name = entrypoint.split(":", 1)
    module = importlib.import_module(module_name)
    agent_cls = getattr(module, symbol_name)
    if not issubclass(agent_cls, Agent):
        raise TypeError(f"{entrypoint} is not an Agent subclass")
    return agent_cls


def _load_manifest(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_runtime_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"agents": []}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def _write_runtime_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")


def _find_state_agent(state: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    for item in state["agents"]:
        if item["manifest"]["agent_id"] == agent_id:
            return item
    return None


def _bootstrap_runtime(platform: AgentFabricPlatform, state: dict[str, Any]) -> None:
    for item in state["agents"]:
        signer = item["signer"]
        key = item["key"]
        manifest = item["manifest"]
        signature = item["signature"]
        payload = base64.b64decode(item["payload_b64"].encode("utf-8"))
        platform.runtime.integrity_verifier.register_signer_key(signer, key)
        platform.runtime.install(
            manifest_payload=manifest,
            package_payload=payload,
            signature=signature,
            signer_id=signer,
            factory=_factory_from_entrypoint(manifest.get("entrypoint", "agentfabric.cli:EchoAgent")),
        )
        if item["state"] == "loaded":
            platform.runtime.load(manifest["agent_id"])
        if item["state"] == "suspended":
            platform.runtime.load(manifest["agent_id"])
            platform.runtime.suspend(manifest["agent_id"])


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    platform = AgentFabricPlatform()
    runtime_state = _read_runtime_state()
    _bootstrap_runtime(platform, runtime_state)
    platform.runtime.tool_router.register_tool("llm.mock", "tool.llm.invoke", lambda arg: {"text": arg.get("prompt", "")})

    if args.command == "seed-dev":
        platform.registry.register_developer_signing_secret(args.developer, args.secret)
        print(json.dumps({"status": "ok", "developer": args.developer}))
        return 0

    if args.command == "install":
        manifest = _load_manifest(args.manifest)
        payload = args.payload.encode("utf-8")
        platform.runtime.integrity_verifier.register_signer_key(args.signer, args.key)
        signature = args.signature or platform.runtime.integrity_verifier.sign(args.signer, payload)
        factory = _factory_from_entrypoint(manifest.get("entrypoint", "agentfabric.cli:EchoAgent"))
        installed = platform.runtime.install(
            manifest_payload=manifest,
            package_payload=payload,
            signature=signature,
            signer_id=args.signer,
            factory=factory,
        )
        existing = _find_state_agent(runtime_state, installed.agent_id)
        record = {
            "manifest": manifest,
            "payload_b64": base64.b64encode(payload).decode("utf-8"),
            "signature": signature,
            "signer": args.signer,
            "key": args.key,
            "state": "installed",
        }
        if existing:
            runtime_state["agents"].remove(existing)
        runtime_state["agents"].append(record)
        _write_runtime_state(runtime_state)
        print(json.dumps({"status": "installed", "agent_id": installed.agent_id}))
        return 0

    if args.command == "load":
        platform.runtime.load(args.agent_id)
        existing = _find_state_agent(runtime_state, args.agent_id)
        if existing:
            existing["state"] = "loaded"
            _write_runtime_state(runtime_state)
        print(json.dumps({"status": "loaded", "agent_id": args.agent_id}))
        return 0

    if args.command == "run":
        request_payload = json.loads(args.request)
        envelope = platform.runtime.run(
            agent_id=args.agent_id,
            request=request_payload,
            user_id=args.user,
            session_id=args.session,
        )
        print(envelope.to_json())
        return 0

    if args.command == "suspend":
        platform.runtime.suspend(args.agent_id)
        existing = _find_state_agent(runtime_state, args.agent_id)
        if existing:
            existing["state"] = "suspended"
            _write_runtime_state(runtime_state)
        print(json.dumps({"status": "suspended", "agent_id": args.agent_id}))
        return 0

    if args.command == "uninstall":
        platform.runtime.uninstall(args.agent_id)
        existing = _find_state_agent(runtime_state, args.agent_id)
        if existing:
            runtime_state["agents"].remove(existing)
            _write_runtime_state(runtime_state)
        print(json.dumps({"status": "uninstalled", "agent_id": args.agent_id}))
        return 0

    if args.command == "agent-list":
        print(json.dumps({"items": platform.runtime.list_agents()}))
        return 0

    if args.command == "publish":
        digest = sha256(args.payload.encode("utf-8")).hexdigest()
        secret = "dev-secret"
        platform.registry.register_developer_signing_secret(args.developer, secret)
        signature = sha256(f"{args.developer}:{digest}:{secret}".encode("utf-8")).hexdigest()
        upload = PackageUpload(
            package_id=args.package,
            version=args.version,
            namespace=args.namespace,
            category=args.category,
            permissions=tuple(args.permissions),
            manifest=_registry_manifest_for(args.package, args.permissions),
            payload=args.payload.encode("utf-8"),
            signature=signature,
        )
        package = platform.registry.publish(args.developer, upload)
        print(json.dumps({"status": "published", "fqid": package.fqid}))
        return 0

    if args.command == "list":
        results = platform.registry.list_packages(
            query=args.query,
            category=args.category,
            required_permissions=set(args.permissions) if args.permissions else None,
        )
        print(json.dumps(results, default=str))
        return 0

    if args.command == "meter-run":
        platform.billing.enqueue(
            MeterEvent(
                event_type="run",
                tenant_id=args.tenant,
                actor_id=args.actor,
                package_fqid=args.fqid,
                idempotency_key=args.idempotency_key,
            )
        )
        platform.billing.process_queue()
        print(json.dumps(platform.billing.build_invoice(args.tenant)))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
