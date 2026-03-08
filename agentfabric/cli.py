"""CLI for operating AgentFabric phase 2-4 scaffolding."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from typing import Any

from agentfabric.phase2.models import MeterEvent, PackageUpload
from agentfabric.platform import AgentFabricPlatform


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentfabric")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed-dev", help="register developer signing secret")
    seed.add_argument("--developer", required=True)
    seed.add_argument("--secret", required=True)

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


def _manifest_for(package_name: str, permissions: list[str]) -> dict[str, Any]:
    return {
        "manifest_version": "v1",
        "name": package_name,
        "description": f"{package_name} package",
        "entrypoint": "agent.py:run",
        "permissions": permissions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    platform = AgentFabricPlatform()

    if args.command == "seed-dev":
        platform.registry.register_developer_signing_secret(args.developer, args.secret)
        print(json.dumps({"status": "ok", "developer": args.developer}))
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
            manifest=_manifest_for(args.package, args.permissions),
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
