"""Core business services backed by SQLAlchemy + queue + integrations."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentfabric.errors import ConflictError, NotFoundError, ValidationError
from agentfabric.server.models import AuditEvent, BillingEvent, Install, InvoiceLine, Package, PaymentRecord
from agentfabric.server.payments import MockPaymentProcessor, PaymentProcessor
from agentfabric.server.queue import QueueBackend, QueueItem, SqlQueueStore
from agentfabric.server.signing import CosignVerifier, DigestFallbackVerifier


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class PackageService:
    def __init__(self, db: Session, signing_verifier=None) -> None:
        self.db = db
        self.signing_verifier = signing_verifier or DigestFallbackVerifier()

    def publish(
        self,
        *,
        namespace: str,
        package_id: str,
        version: str,
        category: str,
        permissions: list[str],
        manifest: dict,
        payload: bytes,
        signature: str,
        signer_id: str,
    ) -> Package:
        existing = self.db.execute(
            select(Package).where(
                Package.namespace == namespace,
                Package.package_id == package_id,
                Package.version == version,
            )
        ).scalar_one_or_none()
        if existing:
            raise ConflictError("package version already exists")
        verification = self.signing_verifier.verify_blob(payload=payload, signature=signature)
        package = Package(
            namespace=namespace,
            package_id=package_id,
            version=version,
            category=category,
            permissions_csv=",".join(sorted(set(permissions))),
            manifest_json=json.dumps(manifest, sort_keys=True),
            payload_digest=verification.payload_digest,
            signature=signature,
            sbom_json=json.dumps(
                {
                    "component": package_id,
                    "version": version,
                    "artifact_sha256": verification.payload_digest,
                    "signer": signer_id,
                    "verified_by": verification.verifier,
                },
                sort_keys=True,
            ),
        )
        self.db.add(package)
        self.db.flush()
        return package

    def list_packages(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        required_permissions: set[str] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        subq = (
            select(
                Package.namespace,
                Package.package_id,
                func.max(Package.created_at).label("max_created"),
            )
            .group_by(Package.namespace, Package.package_id)
            .subquery()
        )
        stmt = (
            select(Package)
            .join(
                subq,
                (Package.namespace == subq.c.namespace)
                & (Package.package_id == subq.c.package_id)
                & (Package.created_at == subq.c.max_created),
            )
            .order_by(Package.created_at.desc())
        )
        rows = self.db.execute(stmt).scalars().all()
        filtered = []
        for item in rows:
            if query and query.lower() not in item.package_id.lower():
                continue
            if category and item.category != category:
                continue
            perms = {p for p in item.permissions_csv.split(",") if p}
            if required_permissions and not required_permissions.issubset(perms):
                continue
            filtered.append(item)
        total = len(filtered)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        items = [
            {
                "namespace": item.namespace,
                "package_id": item.package_id,
                "version": item.version,
                "category": item.category,
                "permissions": [p for p in item.permissions_csv.split(",") if p],
                "payload_digest": item.payload_digest,
                "created_at": item.created_at.isoformat(),
            }
            for item in filtered[start:end]
        ]
        return {"items": items, "page": page, "page_size": page_size, "total": total, "total_pages": total_pages}

    def install(self, *, tenant_id: str, user_id: str, namespace: str, package_id: str, version: str | None = None) -> Install:
        stmt = select(Package).where(Package.namespace == namespace, Package.package_id == package_id)
        if version:
            stmt = stmt.where(Package.version == version)
        package = self.db.execute(stmt.order_by(Package.created_at.desc())).scalars().first()
        if not package:
            raise NotFoundError("package not found")
        install = Install(tenant_id=tenant_id, user_id=user_id, package_fqid=f"{package.namespace}/{package.package_id}:{package.version}")
        self.db.add(install)
        self.db.flush()
        return install


class BillingService:
    PRICING = {"install": 0.05, "run": 0.01, "subscription_month": 29.0}

    def __init__(self, db: Session, payment_processor: PaymentProcessor | None = None) -> None:
        self.db = db
        self.payment_processor = payment_processor or MockPaymentProcessor()

    def record_event(self, *, tenant_id: str, actor_id: str, event_type: str, package_fqid: str, idempotency_key: str) -> bool:
        row = self.db.get(BillingEvent, idempotency_key)
        if row:
            return False
        self.db.add(
            BillingEvent(
                idempotency_key=idempotency_key,
                tenant_id=tenant_id,
                actor_id=actor_id,
                event_type=event_type,
                package_fqid=package_fqid,
            )
        )
        self.db.flush()
        return True

    def build_invoice(self, tenant_id: str) -> dict:
        rows = self.db.execute(
            select(BillingEvent.event_type, func.count(BillingEvent.idempotency_key))
            .where(BillingEvent.tenant_id == tenant_id)
            .group_by(BillingEvent.event_type)
        ).all()
        lines = []
        total = 0.0
        for event_type, qty in rows:
            qty_int = int(qty)
            price = self.PRICING.get(event_type, 0.0)
            subtotal = round(qty_int * price, 4)
            total += subtotal
            lines.append({"event_type": event_type, "quantity": qty_int, "unit_price": price, "subtotal": subtotal})
        return {"tenant_id": tenant_id, "lines": lines, "total": round(total, 4)}

    def settle_invoice(self, tenant_id: str, *, currency: str, idempotency_key: str) -> dict:
        invoice = self.build_invoice(tenant_id)
        payment = self.payment_processor.charge(
            tenant_id=tenant_id,
            amount=invoice["total"],
            currency=currency,
            idempotency_key=idempotency_key,
        )
        self.db.add(
            PaymentRecord(
                tenant_id=tenant_id,
                provider=payment.provider,
                provider_txn_id=payment.provider_txn_id,
                amount=payment.amount,
                currency=payment.currency,
                idempotency_key=idempotency_key,
            )
        )
        self.db.add(
            InvoiceLine(
                tenant_id=tenant_id,
                event_type="settlement",
                quantity=1,
                unit_price=payment.amount,
                subtotal=payment.amount,
            )
        )
        self.db.flush()
        return {"invoice": invoice, "payment": asdict(payment)}


class QueueService:
    def __init__(self, db: Session, backend: QueueBackend) -> None:
        self.db = db
        self.backend = backend
        self.store = SqlQueueStore(db)

    def enqueue(self, queue_name: str, payload: dict) -> QueueItem:
        item = self.backend.enqueue(queue_name, payload)
        self.store.record_enqueue(queue_name, payload, item.message_id)
        return item

    def dequeue(self, queue_name: str) -> QueueItem | None:
        item = self.backend.dequeue(queue_name)
        if item is None:
            return None
        self.store.mark_processing(item.message_id)
        self.store.mark_done(item.message_id)
        return item


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def append(self, *, actor_id: str, action: str, target: str, metadata: dict | None = None) -> dict:
        metadata = metadata or {}
        previous = self.db.execute(select(AuditEvent).order_by(AuditEvent.id.desc())).scalars().first()
        previous_hash = previous.event_hash if previous else "GENESIS"
        material = f"{actor_id}|{action}|{target}|{metadata}|{previous_hash}"
        event_hash = sha256(material.encode("utf-8")).hexdigest()
        event = AuditEvent(
            actor_id=actor_id,
            action=action,
            target=target,
            metadata_json=json.dumps(metadata, sort_keys=True),
            previous_hash=previous_hash,
            event_hash=event_hash,
        )
        self.db.add(event)
        self.db.flush()
        return {"previous_hash": previous_hash, "event_hash": event_hash}
