"""
CLI entrypoint: agentfabric install | run | list. Config file for LLM endpoint and runtime options.
Exit codes: 0 success, 1 usage/error, 2 not found.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Allow running before install
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentfabric.runtime.manifest import load_manifest
from agentfabric.runtime.orchestrator import Orchestrator
from agentfabric.runtime.audit import AuditLog
from agentfabric.runtime.verification import verify_signature


EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_NOT_FOUND = 2


def _config_path() -> Path:
    return Path(os.environ.get("AGENTFABRIC_CONFIG", os.path.expanduser("~/.agentfabric/config.json")))


def load_config() -> dict:
    p = _config_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _agents_dir() -> Path:
    return Path(os.environ.get("AGENTFABRIC_AGENTS_DIR", os.path.expanduser("~/.agentfabric/agents")))


def cmd_list(args: argparse.Namespace) -> int:
    """List installed agents."""
    base = _agents_dir()
    if not base.exists():
        print("No agents installed.", file=sys.stderr)
        return EXIT_SUCCESS
    found = False
    for d in sorted(base.iterdir()):
        if d.is_dir():
            manifest_path = d / "manifest.yaml"
            if not manifest_path.exists():
                manifest_path = d / "manifest.json"
            if manifest_path.exists():
                try:
                    m = load_manifest(manifest_path)
                    print(f"{m.name}\t{m.version}\t{m.description[:50]}...")
                    found = True
                except Exception:
                    print(f"{d.name}\t(invalid manifest)", file=sys.stderr)
    if not found:
        print("No agents installed.")
    return EXIT_SUCCESS


def cmd_install(args: argparse.Namespace) -> int:
    """Install an agent from a local path (directory with manifest)."""
    source = Path(args.path).resolve()
    if not source.exists():
        print(f"Path not found: {source}", file=sys.stderr)
        return EXIT_NOT_FOUND
    manifest_path = source / "manifest.yaml"
    if not manifest_path.exists():
        manifest_path = source / "manifest.json"
    if not manifest_path.exists():
        print("No manifest.yaml or manifest.json in path.", file=sys.stderr)
        return EXIT_ERROR
    try:
        manifest = load_manifest(manifest_path)
    except Exception as e:
        print(f"Invalid manifest: {e}", file=sys.stderr)
        return EXIT_ERROR
    valid, err = verify_signature(source, manifest.raw)
    if not valid:
        print(f"Verification failed: {err}", file=sys.stderr)
        return EXIT_ERROR
    dest = _agents_dir() / manifest.name
    dest.mkdir(parents=True, exist_ok=True)
    # Simple copy: no packaging yet
    import shutil
    for f in source.rglob("*"):
        if f.is_file() and ".git" not in f.parts:
            rel = f.relative_to(source)
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest / rel)
    audit = AuditLog(path=os.environ.get("AGENTFABRIC_AUDIT_LOG"))
    audit.log_install(manifest.name, manifest.version, str(dest), True)
    print(f"Installed {manifest.name}@{manifest.version}")
    return EXIT_SUCCESS


def cmd_run(args: argparse.Namespace) -> int:
    """Run an agent by id with optional input JSON."""
    agent_id = args.agent_id
    base = _agents_dir()
    agent_path = base / agent_id
    if not agent_path.exists() or not agent_path.is_dir():
        print(f"Agent not found: {agent_id}", file=sys.stderr)
        return EXIT_NOT_FOUND
    manifest_path = agent_path / "manifest.yaml"
    if not manifest_path.exists():
        manifest_path = agent_path / "manifest.json"
    if not manifest_path.exists():
        print("Agent manifest missing.", file=sys.stderr)
        return EXIT_NOT_FOUND
    try:
        manifest = load_manifest(manifest_path)
    except Exception as e:
        print(f"Invalid manifest: {e}", file=sys.stderr)
        return EXIT_ERROR
    config = load_config()
    orchestrator = Orchestrator(
        timeout_seconds=float(config.get("timeout_seconds", 60)),
        max_tool_calls_per_run=int(config.get("max_tool_calls", 20)),
    )
    # Stub runner: echoes input as output (real agents are loaded via entrypoint in future)
    def stub_runner(req):
        rid = req.get("id", "")
        return {"type": "run_response", "id": f"resp-{rid}", "request_id": rid, "success": True, "output": req.get("input", {}), "error": None, "events": []}
    orchestrator.register_agent(manifest, stub_runner)
    input_data = {}
    if args.input:
        try:
            input_data = json.loads(args.input)
        except json.JSONDecodeError:
            input_data = {"query": args.input}
    else:
        input_data = {"query": ""}
    try:
        response = asyncio.run(orchestrator.run(agent_id, input_data))
    except Exception as e:
        print(str(e), file=sys.stderr)
        return EXIT_ERROR
    if response.get("success"):
        print(json.dumps(response.get("output") or {}))
        return EXIT_SUCCESS
    print(response.get("error", {}).get("message", "Run failed"), file=sys.stderr)
    return EXIT_ERROR


def main() -> int:
    parser = argparse.ArgumentParser(prog="agentfabric", description="AgentFabric CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List installed agents")
    install_p = sub.add_parser("install", help="Install an agent from a path")
    install_p.add_argument("path", help="Path to agent directory (with manifest)")
    run_p = sub.add_parser("run", help="Run an agent")
    run_p.add_argument("agent_id", help="Agent id (e.g. my_agent)")
    run_p.add_argument("input", nargs="?", help="Input JSON or string")
    args = parser.parse_args()
    if args.command == "list":
        return cmd_list(args)
    if args.command == "install":
        return cmd_install(args)
    if args.command == "run":
        return cmd_run(args)
    return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
