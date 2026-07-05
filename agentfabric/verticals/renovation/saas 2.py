"""SaaS readiness helpers for RenovationOS.

These adapters are intentionally local and deterministic. They define the
interfaces needed by production providers without coupling the cockpit to an
external PDF, file, notification, calendar, or payment service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import re

from agentfabric.enterprise import TenantContext
from agentfabric.persistence import PersistenceStore


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix: str, *parts: object) -> str:
    digest = sha256("|".join(str(part) for part in parts).encode()).hexdigest()
    return f"{prefix}-{digest[:20]}"


def _pdf_escape(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_line(y: int, text: str, size: int = 10) -> str:
    return f"BT /F1 {size} Tf 50 {y} Td ({_pdf_escape(text[:110])}) Tj ET"


class ProposalPdfService:
    def render(self, proposal_record: dict[str, object]) -> bytes:
        artifact = dict(proposal_record.get("artifact", proposal_record))
        customer = dict(artifact.get("customer", {}))
        project = dict(artifact.get("project", {}))
        estimate = dict(artifact.get("estimate", {}))
        scope = list(artifact.get("scope_of_work", [])) or [artifact.get("scope_description", "Renovation scope")]
        line_items = list(estimate.get("line_items", estimate.get("items", [])))
        subtotal = float(estimate.get("subtotal", estimate.get("total", 0)) or 0)
        tax = float(estimate.get("tax", 0) or 0)
        total = float(estimate.get("total", estimate.get("grand_total", subtotal + tax)) or 0)
        lines = [
            "RenovationOS Proposal",
            "Company Branding Placeholder",
            f"Proposal: {artifact.get('proposal_id', proposal_record.get('record_id', 'proposal'))}",
            f"Customer: {customer.get('name', customer.get('customer_id', '-'))}",
            f"Email: {customer.get('email', '-')}",
            f"Phone: {customer.get('phone', '-')}",
            f"Project: {project.get('title', project.get('project_id', '-'))}",
            f"Property: {project.get('property_address', customer.get('address', '-'))}",
            "",
            "Scope",
            *[f"- {item}" for item in scope[:10]],
            "",
            "Line Items",
        ]
        if line_items:
            for item in line_items[:12]:
                item_dict = dict(item)
                description = item_dict.get("description", item_dict.get("name", "Work item"))
                amount = float(item_dict.get("amount", item_dict.get("total", 0)) or 0)
                lines.append(f"- {description}: ${amount:.2f}")
        else:
            lines.append(f"- Renovation work: ${subtotal:.2f}")
        lines.extend(
            [
                "",
                f"Subtotal: ${subtotal:.2f}",
                f"Tax: ${tax:.2f}",
                f"Total: ${total:.2f}",
                "",
                "Terms",
                "Payment schedule, warranty, and change order terms to be finalized before production use.",
                "",
                "Acceptance",
                "Customer Signature: ____________________",
                "Date: ____________________",
            ]
        )
        content = "\n".join(_pdf_line(760 - index * 18, line, 16 if index == 0 else 10) for index, line in enumerate(lines[:38]))
        stream = content.encode()
        objects = [
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj",
            b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
            f"5 0 obj << /Length {len(stream)} >> stream\n".encode() + stream + b"\nendstream endobj",
        ]
        pdf = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for obj in objects:
            offsets.append(len(pdf))
            pdf.extend(obj + b"\n")
        xref = len(pdf)
        pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
        for offset in offsets[1:]:
            pdf.extend(f"{offset:010d} 00000 n \n".encode())
        pdf.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
        return bytes(pdf)


class LocalAttachmentStore:
    allowed_entities = {"customer", "lead", "estimate", "proposal", "job", "invoice", "payment"}

    def __init__(self, root: str | Path, persistence: PersistenceStore) -> None:
        self.root = Path(root)
        self.persistence = persistence

    def save(
        self,
        ctx: TenantContext,
        entity_type: str,
        entity_id: str,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> dict[str, object]:
        if entity_type not in self.allowed_entities:
            raise ValueError("unsupported renovation attachment entity")
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip("-") or "attachment.bin"
        digest = sha256(content).hexdigest()
        attachment_id = stable_id("attachment", ctx.tenant_id, entity_type, entity_id, safe_name, digest)
        path = self.root / ctx.tenant_id / entity_type / entity_id / f"{attachment_id}-{safe_name}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        now = utc_now()
        record = {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": ctx.principal_id,
            "created_at": now,
            "updated_at": now,
            "artifact": {
                "attachment_id": attachment_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "filename": safe_name,
                "content_type": content_type or "application/octet-stream",
                "size_bytes": len(content),
                "sha256": digest,
                "storage_path": str(path),
            },
        }
        self.persistence.put("renovation_attachments", attachment_id, record)
        return record

    def list(self, ctx: TenantContext, entity_type: str | None = None, entity_id: str | None = None) -> dict[str, object]:
        items = self.persistence.list_tenant("renovation_attachments", ctx.tenant_id)
        if entity_type:
            items = [item for item in items if dict(item.get("artifact", {})).get("entity_type") == entity_type]
        if entity_id:
            items = [item for item in items if dict(item.get("artifact", {})).get("entity_id") == entity_id]
        return {"items": items, "total": len(items)}


@dataclass(frozen=True)
class StubResult:
    provider: str
    status: str
    reference_id: str
    payload: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "status": self.status,
            "reference_id": self.reference_id,
            "payload": self.payload,
        }


class LocalNotificationProvider:
    event_types = {
        "proposal_sent",
        "proposal_accepted",
        "invoice_sent",
        "payment_received",
        "schedule_changed",
        "job_status_updated",
    }

    def send(self, tenant_id: str, event_type: str, payload: dict[str, object]) -> StubResult:
        if event_type not in self.event_types:
            raise ValueError("unsupported renovation notification event")
        return StubResult(
            provider="local-log",
            status="queued",
            reference_id=stable_id("notification", tenant_id, event_type, payload),
            payload={"event_type": event_type, **payload},
        )


class LocalCalendarProvider:
    def sync(self, tenant_id: str, schedule_item: dict[str, object]) -> StubResult:
        schedule_id = str(schedule_item.get("schedule_id", "schedule"))
        return StubResult(
            provider="local-calendar",
            status="synced",
            reference_id=stable_id("calendar", tenant_id, schedule_id),
            payload={"schedule_id": schedule_id, "external_event_id": f"local-{schedule_id}"},
        )


class LocalPaymentProvider:
    def link(self, tenant_id: str, invoice: dict[str, object]) -> StubResult:
        invoice_id = str(invoice.get("invoice_id", "invoice"))
        return StubResult(
            provider="local-payment",
            status="created",
            reference_id=stable_id("payment-link", tenant_id, invoice_id),
            payload={"invoice_id": invoice_id, "payment_url": f"https://payments.local/{tenant_id}/{invoice_id}"},
        )

    def status(self, tenant_id: str, invoice_id: str, status: str) -> StubResult:
        return StubResult(
            provider="local-payment",
            status="updated",
            reference_id=stable_id("payment-status", tenant_id, invoice_id, status),
            payload={"invoice_id": invoice_id, "payment_status": status},
        )
