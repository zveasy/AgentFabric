"""Production control plane integrating P0, P1, and P2 services."""

from __future__ import annotations

import importlib
import math
from dataclasses import asdict
from hashlib import sha256
from typing import Any, Callable

from agentfabric.errors import AuthorizationError, ValidationError
from agentfabric.phase1.runtime import AgentOrchestrator
from agentfabric.phase1.sdk import Agent
from agentfabric.phase2.models import AgentPackage, MeterEvent, PackageUpload, Rating
from agentfabric.phase4.rbac import RbacService
from agentfabric.production.authn import TokenAuthService
from agentfabric.production.compliance import ComplianceService, LegalPolicyService
from agentfabric.production.marketplace import ModerationService, SettlementService
from agentfabric.production.ops import BackupManager, PrometheusExporter, RetryWorker, TraceExporter
from agentfabric.production.security_pipeline import PackageSecurityPipeline, SignaturePolicy
from agentfabric.production.store import ProductionStore


class ProductionControlPlane:
    """Durable application service for AgentFabric operations."""

    BILLING_PRICES = {
        "install": 0.05,
        "run": 0.01,
        "subscription_month": 29.0,
    }

    def __init__(self, *, db_path: str = "agentfabric.db") -> None:
        self.store = ProductionStore(db_path=db_path)
        self.runtime = AgentOrchestrator()
        self.auth = TokenAuthService(self.store)
        self.security = PackageSecurityPipeline(signature_policy=SignaturePolicy(require_trusted_signer=False))
        self.moderation = ModerationService(self.store)
        self.settlement = SettlementService(self.store)
        self.compliance = ComplianceService(self.store)
        self.legal = LegalPolicyService(self.store)
        self.backups = BackupManager(db_path=db_path)
        self.prometheus = PrometheusExporter()
        self.trace_exporter = TraceExporter(output_file="artifacts/traces.jsonl")
        self.retry_worker = RetryWorker()
        self._rbac_reference = RbacService()
        self._runtime_factories: dict[str, Callable[[], Agent]] = {}
        self._bootstrap_runtime_from_store()

    # P0: Hosted control-plane behaviors
    def publish_package(self, developer_id: str, upload: PackageUpload, signer_id: str) -> AgentPackage:
        if developer_id != upload.namespace:
            raise AuthorizationError("developer can only publish under own namespace")
        self.security.integrity_verifier.register_signer_key(signer_id, "managed")
        signature = sha256(f"{signer_id}:{sha256(upload.payload).hexdigest()}:managed".encode("utf-8")).hexdigest()
        if upload.signature != signature:
            raise ValidationError("signature does not match managed signer material")
        sec_report = self.security.validate(
            signer_id=signer_id,
            package_name=upload.package_id,
            version=upload.version,
            payload=upload.payload,
            signature=upload.signature,
        )
        package = AgentPackage(
            package_id=upload.package_id,
            version=upload.version,
            developer_id=developer_id,
            namespace=upload.namespace,
            category=upload.category,
            permissions=upload.permissions,
            manifest=upload.manifest | {"sbom": sec_report["sbom"]},
            payload_digest=sec_report["payload_digest"],
            signature=upload.signature,
        )
        self.store.put_package(package)
        return package

    def list_packages(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        required_permissions: set[str] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        rows = self.store.list_latest_packages(query=query, category=category, required_permissions=required_permissions)
        total = len(rows)
        total_pages = max(1, math.ceil(total / page_size))
        start = (page - 1) * page_size
        end = start + page_size
        items = [asdict(item) for item in rows[start:end]]
        return {"items": items, "page": page, "page_size": page_size, "total": total, "total_pages": total_pages}

    def install_package(self, tenant_id: str, user_id: str, namespace: str, package_id: str, version: str | None = None) -> dict[str, Any]:
        package = self.store.get_package(namespace=namespace, package_id=package_id, version=version)
        install = self.store.add_install(tenant_id=tenant_id, user_id=user_id, package_fqid=package.fqid)
        self.record_billing_event(
            MeterEvent(
                event_type="install",
                tenant_id=tenant_id,
                actor_id=user_id,
                package_fqid=package.fqid,
                idempotency_key=f"install:{tenant_id}:{user_id}:{package.fqid}",
            )
        )
        return {"tenant_id": install.tenant_id, "user_id": install.user_id, "package_fqid": install.package_fqid}

    def record_billing_event(self, event: MeterEvent) -> bool:
        return self.store.record_billing_event(event)

    def build_invoice(self, tenant_id: str) -> dict[str, Any]:
        usage = self.store.usage_counts(tenant_id)
        lines = []
        total = 0.0
        for event_type, quantity in sorted(usage.items()):
            unit_price = self.BILLING_PRICES.get(event_type, 0.0)
            subtotal = round(quantity * unit_price, 4)
            total += subtotal
            lines.append({"event_type": event_type, "quantity": quantity, "unit_price": unit_price, "subtotal": subtotal})
        return {"tenant_id": tenant_id, "lines": lines, "total": round(total, 4)}

    # P0: runtime control with persistence
    def install_runtime_agent(self, *, manifest: dict[str, Any], payload: bytes, signer_id: str, signer_key: str, signature: str) -> str:
        self.runtime.integrity_verifier.register_signer_key(signer_id, signer_key)
        factory = self._factory_from_entrypoint(manifest.get("entrypoint", "agentfabric.cli:EchoAgent"))
        installed = self.runtime.install(
            manifest_payload=manifest,
            package_payload=payload,
            signature=signature,
            signer_id=signer_id,
            factory=factory,
        )
        self._runtime_factories[installed.agent_id] = factory
        self.store.upsert_runtime_agent(
            agent_id=installed.agent_id,
            manifest=manifest,
            payload=payload,
            signature=signature,
            signer_id=signer_id,
            signer_key=signer_key,
            state="installed",
        )
        return installed.agent_id

    def runtime_load(self, agent_id: str) -> None:
        self.runtime.load(agent_id)
        self.store.update_runtime_agent_state(agent_id, "loaded")

    def runtime_run(self, *, agent_id: str, request: dict[str, Any], user_id: str, session_id: str) -> dict[str, Any]:
        envelope = self.runtime.run(agent_id=agent_id, request=request, user_id=user_id, session_id=session_id)
        self.record_billing_event(
            MeterEvent(
                event_type="run",
                tenant_id=user_id,
                actor_id=user_id,
                package_fqid=agent_id,
                idempotency_key=f"run:{agent_id}:{envelope.correlation_id}",
            )
        )
        return {"correlation_id": envelope.correlation_id, "payload": envelope.payload}

    def runtime_suspend(self, agent_id: str) -> None:
        self.runtime.suspend(agent_id)
        self.store.update_runtime_agent_state(agent_id, "suspended")

    def runtime_uninstall(self, agent_id: str) -> None:
        self.runtime.uninstall(agent_id)
        self.store.delete_runtime_agent(agent_id)

    def runtime_agents(self) -> list[dict[str, Any]]:
        return self.runtime.list_agents()

    # P1/P2 enterprise and compliance
    def assign_role(self, principal_id: str, role: str) -> None:
        if role not in self._rbac_reference.ROLE_PERMISSIONS:
            raise ValidationError("unknown role")
        self.store.assign_role(principal_id, role)

    def check_permission(self, principal_id: str, permission: str) -> None:
        roles = self.store.get_roles(principal_id)
        for role in roles:
            if permission in self._rbac_reference.ROLE_PERMISSIONS[role]:
                return
        raise AuthorizationError(f"principal {principal_id} lacks {permission}")

    def create_namespace(self, owner_tenant_id: str, namespace: str) -> None:
        self.store.create_namespace(owner_tenant_id, namespace)

    def grant_namespace_access(self, owner_tenant_id: str, namespace: str, target_tenant_id: str) -> None:
        self.store.grant_namespace_access(owner_tenant_id, namespace, target_tenant_id)

    def check_namespace_access(self, tenant_id: str, namespace: str) -> None:
        if not self.store.has_namespace_access(tenant_id, namespace):
            raise AuthorizationError("tenant has no access to private namespace")

    def append_audit(self, actor_id: str, action: str, target: str, metadata: dict[str, Any] | None = None) -> dict[str, str]:
        metadata = metadata or {}
        previous_hash = self.store.last_audit_hash()
        material = f"{actor_id}|{action}|{target}|{metadata}|{previous_hash}"
        event_hash = sha256(material.encode("utf-8")).hexdigest()
        self.store.append_audit(
            actor_id=actor_id,
            action=action,
            target=target,
            metadata=metadata,
            previous_hash=previous_hash,
            event_hash=event_hash,
        )
        return {"previous_hash": previous_hash, "event_hash": event_hash}

    def verify_audit_integrity(self) -> bool:
        previous_hash = "GENESIS"
        for event in self.store.audit_events():
            material = f"{event['actor_id']}|{event['action']}|{event['target']}|{event['metadata']}|{previous_hash}"
            expected = sha256(material.encode("utf-8")).hexdigest()
            if expected != event["event_hash"] or event["previous_hash"] != previous_hash:
                return False
            previous_hash = event["event_hash"]
        return True

    def submit_review(self, rating: Rating) -> int:
        return self.moderation.submit_review(rating)

    def pending_reviews(self) -> list[dict]:
        return self.moderation.pending()

    def moderate_review(self, review_id: int, approved: bool) -> None:
        self.moderation.moderate(review_id, approved)

    def settle_invoice(self, tenant_id: str, currency: str = "USD") -> dict[str, Any]:
        invoice = self.build_invoice(tenant_id)
        tx = self.settlement.settle_invoice(
            tenant_id=tenant_id,
            total=invoice["total"],
            currency=currency,
            idempotency_key=f"settle:{tenant_id}:{invoice['total']}",
        )
        return {"invoice": invoice, "transaction_id": tx}

    def request_gdpr_deletion(self, tenant_id: str, user_id: str | None, reason: str) -> str:
        return self.compliance.request_deletion(tenant_id=tenant_id, user_id=user_id, reason=reason)

    def process_gdpr_deletions(self) -> list[str]:
        return self.compliance.process_pending_deletions()

    def export_siem_audit(self, output_file: str) -> str:
        return self.compliance.export_audit_for_siem(output_file)

    def publish_legal_document(self, doc_type: str, version: str, content: str) -> None:
        self.legal.publish_document(doc_type, version, content)

    def accept_legal_document(self, doc_type: str, principal_id: str) -> dict[str, str]:
        return self.legal.accept(doc_type, principal_id)

    def metrics_prometheus(self) -> str:
        return self.prometheus.export(self.runtime.metrics)

    def create_backup(self) -> str:
        return self.backups.create_backup()

    # internal
    def _bootstrap_runtime_from_store(self) -> None:
        for item in self.store.list_runtime_agents():
            signer_id = item["signer_id"]
            signer_key = item["signer_key"]
            manifest = item["manifest"]
            self.runtime.integrity_verifier.register_signer_key(signer_id, signer_key)
            factory = self._factory_from_entrypoint(manifest.get("entrypoint", "agentfabric.cli:EchoAgent"))
            self.runtime.install(
                manifest_payload=manifest,
                package_payload=item["payload"],
                signature=item["signature"],
                signer_id=signer_id,
                factory=factory,
            )
            self._runtime_factories[manifest["agent_id"]] = factory
            if item["state"] == "loaded":
                self.runtime.load(manifest["agent_id"])
            elif item["state"] == "suspended":
                self.runtime.load(manifest["agent_id"])
                self.runtime.suspend(manifest["agent_id"])

    @staticmethod
    def _factory_from_entrypoint(entrypoint: str) -> Callable[[], Agent]:
        module_name, symbol_name = entrypoint.split(":", 1)
        module = importlib.import_module(module_name)
        agent_cls = getattr(module, symbol_name)
        if not issubclass(agent_cls, Agent):
            raise ValidationError(f"{entrypoint} is not an Agent subclass")
        return agent_cls
