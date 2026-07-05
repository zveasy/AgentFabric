"""Production-boundary helpers for RenovationOS SaaS integrations.

The concrete providers here are deterministic local implementations. Their
payloads intentionally look like production provider records so email/SMS,
calendar, payment, object storage, and PDF engines can replace them later
without changing the cockpit workflow model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from hashlib import sha256
from pathlib import Path
import re
import smtplib

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
    return f"BT /F1 {size} Tf 50 {y} Td ({_pdf_escape(text[:115])}) Tj ET"


def _simple_pdf(lines: list[str]) -> bytes:
    content = "\n".join(_pdf_line(760 - index * 18, line, 15 if index == 0 else 10) for index, line in enumerate(lines[:39]))
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


class RenovationPdfService:
    def proposal(self, proposal_record: dict[str, object], company_profile: dict[str, object]) -> bytes:
        artifact = dict(proposal_record.get("artifact", proposal_record))
        customer = dict(artifact.get("customer", {}))
        project = dict(artifact.get("project", {}))
        estimate = dict(artifact.get("estimate", {}))
        scope = list(artifact.get("scope_of_work", [])) or [artifact.get("scope_description", "Renovation scope")]
        subtotal = float(estimate.get("subtotal", estimate.get("total", 0)) or 0)
        tax = float(estimate.get("tax", 0) or 0)
        total = float(estimate.get("total", estimate.get("grand_total", subtotal + tax)) or 0)
        lines = [
            "RenovationOS Proposal",
            f"{company_profile.get('company_name', 'Company Branding Placeholder')} | Logo Placeholder",
            f"Proposal: {artifact.get('proposal_id', proposal_record.get('record_id', 'proposal'))}",
            f"Customer: {customer.get('name', customer.get('customer_id', '-'))}",
            f"Email: {customer.get('email', '-')}",
            f"Phone: {customer.get('phone', '-')}",
            f"Project: {project.get('title', project.get('project_id', '-'))}",
            f"Property: {project.get('property_address', customer.get('address', '-'))}",
            "",
            "Scope",
            *[f"- {item}" for item in scope[:9]],
            "",
            "Line Items",
            f"- Renovation work subtotal: ${subtotal:.2f}",
            f"Tax: ${tax:.2f}",
            f"Total: ${total:.2f}",
            "",
            "Terms",
            str(company_profile.get("proposal_terms", "Payment schedule, warranty, and change orders are subject to written approval.")),
            "",
            "Acceptance",
            "Customer Signature: ____________________",
            "Date: ____________________",
        ]
        return _simple_pdf(lines)

    def invoice(
        self,
        invoice_record: dict[str, object],
        company_profile: dict[str, object],
        payment_link: dict[str, object] | None = None,
    ) -> bytes:
        artifact = dict(invoice_record.get("artifact", invoice_record))
        link_payload = dict(payment_link.get("payload", {})) if payment_link else {}
        lines = [
            "RenovationOS Invoice",
            f"{company_profile.get('company_name', 'Company Branding Placeholder')} | Logo Placeholder",
            f"Invoice: {artifact.get('invoice_id', '-')}",
            f"Job: {artifact.get('job_id', '-')}",
            f"Invoice date: {artifact.get('invoice_date', '-')}",
            f"Due date: {artifact.get('due_date', '-')}",
            "",
            "Line Items",
            f"- {artifact.get('description', 'Renovation invoice')}: ${float(artifact.get('amount', 0) or 0):.2f}",
            f"Tax: ${float(artifact.get('tax', 0) or 0):.2f}",
            f"Total: ${float(artifact.get('total', 0) or 0):.2f}",
            f"Paid: ${float(artifact.get('paid_amount', 0) or 0):.2f}",
            f"Invoice balance: ${float(artifact.get('outstanding_balance', 0) or 0):.2f}",
            "",
            "Payment",
            f"Payment link: {link_payload.get('payment_url', 'Not generated')}",
            f"Provider reference: {link_payload.get('provider_reference_id', '-')}",
            "",
            "Terms",
            str(company_profile.get("invoice_terms", "Payment due by the stated due date.")),
        ]
        return _simple_pdf(lines)


ProposalPdfService = RenovationPdfService


class LocalAttachmentStore:
    allowed_entities = {"customer", "lead", "estimate", "proposal", "job", "invoice", "payment"}
    allowed_content_types = {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "text/plain",
        "application/octet-stream",
    }

    def __init__(self, root: str | Path, persistence: PersistenceStore, max_bytes: int = 10_000_000) -> None:
        self.root = Path(root)
        self.persistence = persistence
        self.max_bytes = max_bytes

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
        if len(content) > self.max_bytes:
            raise ValueError("attachment exceeds maximum file size")
        normalized_type = content_type or "application/octet-stream"
        if normalized_type not in self.allowed_content_types:
            raise ValueError("attachment content type is not allowed")
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
                "content_type": normalized_type,
                "size_bytes": len(content),
                "sha256": digest,
                "storage_path": str(path),
                "status": "active",
            },
        }
        self.persistence.put("renovation_attachments", attachment_id, record)
        return record

    def list(
        self,
        ctx: TenantContext,
        entity_type: str | None = None,
        entity_id: str | None = None,
        include_archived: bool = False,
    ) -> dict[str, object]:
        items = self.persistence.list_tenant("renovation_attachments", ctx.tenant_id)
        if entity_type:
            items = [item for item in items if dict(item.get("artifact", {})).get("entity_type") == entity_type]
        if entity_id:
            items = [item for item in items if dict(item.get("artifact", {})).get("entity_id") == entity_id]
        if not include_archived:
            items = [item for item in items if dict(item.get("artifact", {})).get("status", "active") != "archived"]
        return {"items": items, "total": len(items)}

    def get(self, ctx: TenantContext, attachment_id: str, include_archived: bool = False) -> dict[str, object]:
        record = self.persistence.get("renovation_attachments", attachment_id)
        if record is None or record.get("tenant_id") != ctx.tenant_id:
            raise KeyError("attachment not found")
        artifact = dict(record.get("artifact", {}))
        if artifact.get("status") == "archived" and not include_archived:
            raise KeyError("attachment not found")
        return record

    def read(self, ctx: TenantContext, attachment_id: str) -> tuple[dict[str, object], bytes]:
        record = self.get(ctx, attachment_id)
        artifact = dict(record["artifact"])
        path = Path(str(artifact["storage_path"]))
        root = (self.root / ctx.tenant_id).resolve()
        resolved = path.resolve()
        if root not in resolved.parents:
            raise ValueError("attachment path is outside storage root")
        return record, resolved.read_bytes()

    def archive(self, ctx: TenantContext, attachment_id: str) -> dict[str, object]:
        record = self.get(ctx, attachment_id)
        artifact = dict(record["artifact"])
        artifact["status"] = "archived"
        artifact["archived_at"] = utc_now()
        record["artifact"] = artifact
        record["updated_at"] = artifact["archived_at"]
        self.persistence.put("renovation_attachments", attachment_id, record)
        return record


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    status: str
    reference_id: str
    payload: dict[str, object]
    failure_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        value = {
            "provider": self.provider,
            "status": self.status,
            "reference_id": self.reference_id,
            "payload": self.payload,
        }
        if self.failure_reason:
            value["failure_reason"] = self.failure_reason
        return value


StubResult = ProviderResult


class NotificationProvider:
    channels: set[str] = set()

    def validate_config(self, config: dict[str, object]) -> dict[str, object]:
        missing = [field for field in ("from",) if not config.get(field)]
        return {"valid": not missing, "missing": missing, "provider": self.__class__.__name__}


class EmailNotificationProvider(NotificationProvider):
    channels = {"email"}


class SmtpEmailProvider(EmailNotificationProvider):
    required_fields = ("smtp_host", "sender")

    def validate_config(self, config: dict[str, object]) -> dict[str, object]:
        missing = [field for field in self.required_fields if not config.get(field)]
        port = int(config.get("smtp_port", 587) or 587)
        live_enabled = bool(config.get("send_live") or config.get("live_enabled"))
        checklist = [
            {"key": "smtp_host", "label": "SMTP host", "configured": bool(config.get("smtp_host"))},
            {"key": "smtp_port", "label": "SMTP port", "configured": 0 < port < 65536},
            {"key": "sender", "label": "Verified sender email", "configured": bool(config.get("sender"))},
            {"key": "smtp_username", "label": "SMTP username", "configured": bool(config.get("smtp_username")), "optional": True},
            {"key": "smtp_password", "label": "SMTP password", "configured": bool(config.get("smtp_password")), "optional": True},
        ]
        return {
            "valid": not missing and 0 < port < 65536,
            "missing": missing,
            "provider": "smtp-email",
            "channel": "email",
            "mode": "live" if live_enabled else "stub",
            "status": "configured" if not missing else "missing_config",
            "checklist": checklist,
            "setup_instructions": "Set SMTP host, port, and verified sender. Enable live SMTP only after testing credentials and SPF/DKIM.",
        }

    def send(self, tenant_id: str, event_type: str, payload: dict[str, object]) -> ProviderResult:
        config = {**dict(payload.get("config", {})), **payload}
        recipients = _as_string_list(config.get("recipients") or config.get("to"))
        cc = _as_string_list(config.get("cc"))
        bcc = _as_string_list(config.get("bcc"))
        sender = str(config.get("sender") or config.get("from") or "")
        reply_to = str(config.get("reply_to") or "")
        subject = str(config.get("subject") or f"RenovationOS {event_type.replace('_', ' ')}")
        body = str(config.get("body") or config.get("text_body") or "")
        html_body = str(config.get("html_body") or "")
        reference_id = stable_id("smtp-email", tenant_id, event_type, sender, recipients, cc, bcc, subject, body, html_body)
        provider_reference_id = stable_id("provider-email", tenant_id, reference_id)
        if config.get("simulate_failure"):
            reason = str(config.get("failure_reason", "simulated SMTP delivery failure"))
            return ProviderResult(
                provider="smtp-email",
                status="failed",
                reference_id=reference_id,
                payload=self._payload(event_type, sender, reply_to, recipients, cc, bcc, subject, body, html_body, provider_reference_id, "failed", False),
                failure_reason=reason,
            )
        validation = self.validate_config(config)
        if not validation["valid"] or not recipients:
            missing = list(validation.get("missing", []))
            if not recipients:
                missing.append("recipients")
            reason = f"missing SMTP config: {', '.join(missing)}"
            return ProviderResult(
                provider="smtp-email",
                status="failed",
                reference_id=reference_id,
                payload=self._payload(event_type, sender, reply_to, recipients, cc, bcc, subject, body, html_body, provider_reference_id, "failed", False),
                failure_reason=reason,
            )
        live_enabled = bool(config.get("send_live") or config.get("live_enabled"))
        if live_enabled:
            try:
                message = EmailMessage()
                message["From"] = sender
                message["To"] = ", ".join(recipients)
                if cc:
                    message["Cc"] = ", ".join(cc)
                message["Subject"] = subject
                if reply_to:
                    message["Reply-To"] = reply_to
                message.set_content(body or " ")
                if html_body:
                    message.add_alternative(html_body, subtype="html")
                with smtplib.SMTP(str(config["smtp_host"]), int(config.get("smtp_port", 587) or 587), timeout=10) as smtp:
                    if config.get("smtp_starttls", True):
                        smtp.starttls()
                    if config.get("smtp_username"):
                        smtp.login(str(config["smtp_username"]), str(config.get("smtp_password", "")))
                    smtp.send_message(message)
            except Exception as exc:
                return ProviderResult(
                    provider="smtp-email",
                    status="failed",
                    reference_id=reference_id,
                    payload=self._payload(event_type, sender, reply_to, recipients, cc, bcc, subject, body, html_body, provider_reference_id, "failed", live_enabled),
                    failure_reason=str(exc),
                )
        return ProviderResult(
            provider="smtp-email",
            status=str(config.get("deterministic_status", "sent" if live_enabled else "stubbed")),
            reference_id=reference_id,
            payload=self._payload(
                event_type,
                sender,
                reply_to,
                recipients,
                cc,
                bcc,
                subject,
                body,
                html_body,
                provider_reference_id,
                "sent" if live_enabled else "stubbed",
                live_enabled,
            ),
        )

    def _payload(
        self,
        event_type: str,
        sender: str,
        reply_to: str,
        recipients: list[str],
        cc: list[str],
        bcc: list[str],
        subject: str,
        body: str,
        html_body: str,
        provider_reference_id: str,
        delivery_status: str,
        live_enabled: bool,
    ) -> dict[str, object]:
        return {
            "event_type": event_type,
            "channel": "email",
            "sender": sender,
            "reply_to": reply_to,
            "recipients": recipients,
            "cc": cc,
            "bcc": bcc,
            "subject": subject,
            "body": body,
            "html_body": html_body,
            "delivery_status": delivery_status,
            "live_enabled": live_enabled,
            "provider_reference_id": provider_reference_id,
            "sent_at": utc_now(),
        }


class SmsNotificationProvider(NotificationProvider):
    channels = {"sms"}

    def validate_config(self, config: dict[str, object]) -> dict[str, object]:
        provider = str(config.get("provider", "sms"))
        missing = []
        if not config.get("sender_id"):
            missing.append("sender_id")
        if provider == "twilio":
            for field in ("account_sid", "auth_token"):
                if not config.get(field):
                    missing.append(field)
        checklist = [
            {"key": "sender_id", "label": "Sender phone number or messaging service", "configured": bool(config.get("sender_id"))},
            {"key": "account_sid", "label": "Provider account SID", "configured": bool(config.get("account_sid")), "optional": provider != "twilio"},
            {"key": "auth_token", "label": "Provider auth token", "configured": bool(config.get("auth_token")), "optional": provider != "twilio"},
        ]
        return {
            "valid": not missing,
            "missing": missing,
            "provider": "twilio-sms" if provider == "twilio" else "sms-shell",
            "channel": "sms",
            "mode": "live-ready" if provider == "twilio" else "stub",
            "status": "configured" if not missing else "missing_config",
            "checklist": checklist,
            "setup_instructions": "Configure a sender, account SID, and token before enabling live SMS delivery.",
        }

    def send(self, tenant_id: str, event_type: str, payload: dict[str, object]) -> ProviderResult:
        config = {**dict(payload.get("config", {})), **payload}
        recipients = _as_string_list(config.get("recipients") or config.get("to"))
        sender_id = str(config.get("sender_id") or "")
        body = str(config.get("body") or config.get("message") or "")
        provider_name = "twilio-sms" if config.get("provider") == "twilio" else "sms-shell"
        reference_id = stable_id("sms", tenant_id, event_type, sender_id, recipients, body)
        provider_reference_id = stable_id("provider-sms", tenant_id, reference_id)
        if config.get("simulate_failure"):
            reason = str(config.get("failure_reason", "simulated SMS provider failure"))
            return ProviderResult(
                provider=provider_name,
                status="failed",
                reference_id=reference_id,
                payload={
                    "event_type": event_type,
                    "channel": "sms",
                    "sender_id": sender_id,
                    "recipients": recipients,
                    "body": body,
                    "delivery_status": "failed",
                    "provider_message_id": provider_reference_id,
                    "provider_reference_id": provider_reference_id,
                    "retry_eligible": bool(config.get("retry_eligible", True)),
                    "sent_at": utc_now(),
                },
                failure_reason=reason,
            )
        validation = self.validate_config(config)
        if not validation["valid"] or not recipients:
            missing = list(validation.get("missing", []))
            if not recipients:
                missing.append("recipients")
            reason = f"missing SMS config: {', '.join(missing)}"
            return ProviderResult(
                provider=provider_name,
                status="failed",
                reference_id=reference_id,
                payload={
                    "event_type": event_type,
                    "channel": "sms",
                    "sender_id": sender_id,
                    "recipients": recipients,
                    "body": body,
                    "delivery_status": "failed",
                    "provider_message_id": provider_reference_id,
                    "provider_reference_id": provider_reference_id,
                    "retry_eligible": True,
                    "sent_at": utc_now(),
                },
                failure_reason=reason,
            )
        return ProviderResult(
            provider=provider_name,
            status=str(config.get("deterministic_status", "queued")),
            reference_id=reference_id,
            payload={
                "event_type": event_type,
                "channel": "sms",
                "sender_id": sender_id,
                "recipients": recipients,
                "body": body,
                "delivery_status": str(config.get("deterministic_status", "queued")),
                "provider_message_id": provider_reference_id,
                "provider_reference_id": provider_reference_id,
                "retry_eligible": False,
                "sent_at": utc_now(),
            },
        )


class LocalNotificationProvider(NotificationProvider):
    channels = {"email", "sms", "portal"}
    event_types = {
        "proposal_sent",
        "proposal_accepted",
        "invoice_sent",
        "payment_received",
        "schedule_changed",
        "job_status_updated",
    }

    def validate_config(self, config: dict[str, object]) -> dict[str, object]:
        channel = str(config.get("channel", "email"))
        provider = str(config.get("provider", "local"))
        if provider == "smtp" or channel == "email" and config.get("smtp_host"):
            return SmtpEmailProvider().validate_config(config)
        if provider in {"sms", "twilio", "text"} or channel == "sms" and config.get("sender_id"):
            return SmsNotificationProvider().validate_config(config)
        return {"valid": channel in self.channels, "missing": [], "provider": "local-log", "channel": channel}

    def send(self, tenant_id: str, event_type: str, payload: dict[str, object]) -> ProviderResult:
        if event_type not in self.event_types:
            raise ValueError("unsupported renovation notification event")
        channel = str(payload.get("channel", "email"))
        if channel not in self.channels:
            raise ValueError("unsupported renovation notification channel")
        provider = str(payload.get("provider", "local"))
        if provider == "smtp" or channel == "email" and payload.get("smtp_host"):
            return SmtpEmailProvider().send(tenant_id, event_type, payload)
        if provider in {"sms", "twilio", "text"} or channel == "sms" and payload.get("sender_id"):
            return SmsNotificationProvider().send(tenant_id, event_type, payload)
        reference_id = stable_id("notification", tenant_id, event_type, channel, payload)
        return ProviderResult(
            provider="local-log",
            status="queued",
            reference_id=reference_id,
            payload={"event_type": event_type, "channel": channel, "sent_at": utc_now(), **payload},
        )


class LocalCalendarProvider:
    def validate_config(self, config: dict[str, object]) -> dict[str, object]:
        provider = str(config.get("provider", "local"))
        checklist = [
            {"key": "provider", "label": "Calendar provider selected", "configured": provider in {"local", "google", "outlook"}},
            {"key": "oauth_client_id", "label": "OAuth client ID", "configured": bool(config.get("oauth_client_id")), "optional": True},
            {"key": "oauth_client_secret", "label": "OAuth client secret", "configured": bool(config.get("oauth_client_secret")), "optional": True},
        ]
        return {
            "valid": provider in {"local", "google", "outlook"},
            "provider": f"{provider}-calendar" if provider in {"google", "outlook"} else provider,
            "missing": [],
            "status": "stubbed" if provider in {"google", "outlook"} else "local_stub",
            "mode": "oauth-ready-stub" if provider in {"google", "outlook"} else "stub",
            "checklist": checklist,
            "setup_instructions": "Create OAuth credentials and grant calendar scopes before enabling live calendar sync.",
        }

    def sync(self, tenant_id: str, schedule_item: dict[str, object], options: dict[str, object] | None = None) -> ProviderResult:
        options = options or {}
        schedule_id = str(schedule_item.get("schedule_id", "schedule"))
        provider = str(options.get("provider", "local"))
        reference_id = stable_id("calendar", tenant_id, schedule_id, options.get("calendar_id", provider))
        operation = str(options.get("operation", "create"))
        if operation not in {"create", "update", "delete", "sync"}:
            raise ValueError("unsupported calendar sync operation")
        event_title = str(options.get("event_title") or schedule_item.get("title") or f"Renovation schedule {schedule_id}")
        start_time = str(options.get("start_time") or schedule_item.get("start_date") or "")
        end_time = str(options.get("end_time") or schedule_item.get("end_date") or start_time)
        retry_count = int(options.get("retry_count", 0) or 0)
        if options.get("simulate_failure"):
            return ProviderResult(
                provider=f"{provider}-calendar" if provider in {"google", "outlook"} else "local-calendar",
                status="failed",
                reference_id=reference_id,
                payload={
                    "schedule_id": schedule_id,
                    "job_id": schedule_item.get("job_id"),
                    "customer_id": schedule_item.get("customer_id"),
                    "event_title": event_title,
                    "operation": operation,
                    "start_time": start_time,
                    "end_time": end_time,
                    "sync_status": "failed",
                    "retry_count": retry_count + 1,
                    "last_sync_at": utc_now(),
                    "external_event_id": None,
                },
                failure_reason=str(options.get("failure_reason", "simulated calendar failure")),
            )
        external_event_id = None if operation == "delete" else str(options.get("external_event_id") or f"{provider}-{schedule_id}")
        sync_status = "deleted" if operation == "delete" else "synced"
        return ProviderResult(
            provider=f"{provider}-calendar" if provider in {"google", "outlook"} else "local-calendar",
            status=sync_status,
            reference_id=reference_id,
            payload={
                "schedule_id": schedule_id,
                "job_id": schedule_item.get("job_id"),
                "customer_id": schedule_item.get("customer_id"),
                "event_title": event_title,
                "operation": operation,
                "start_time": start_time,
                "end_time": end_time,
                "sync_status": sync_status,
                "retry_count": retry_count,
                "external_event_id": external_event_id,
                "last_sync_at": utc_now(),
            },
        )


class LocalPaymentProvider:
    valid_statuses = {"pending", "authorized", "paid", "failed", "refunded", "partial"}
    provider_status_map = {
        "checkout.session.completed": "paid",
        "payment_intent.succeeded": "paid",
        "payment_intent.payment_failed": "failed",
        "charge.refunded": "refunded",
        "invoice.payment_succeeded": "paid",
        "invoice.payment_failed": "failed",
    }

    def validate_config(self, config: dict[str, object]) -> dict[str, object]:
        provider = str(config.get("provider", "local"))
        missing = []
        if provider == "stripe" and config.get("live_enabled"):
            for field in ("secret_key", "webhook_secret"):
                if not config.get(field):
                    missing.append(field)
        checklist = [
            {"key": "secret_key", "label": "Stripe secret key", "configured": bool(config.get("secret_key")), "optional": not config.get("live_enabled")},
            {"key": "webhook_secret", "label": "Webhook signing secret", "configured": bool(config.get("webhook_secret")), "optional": not config.get("live_enabled")},
            {"key": "success_url", "label": "Success URL", "configured": bool(config.get("success_url")), "optional": True},
            {"key": "cancel_url", "label": "Cancel URL", "configured": bool(config.get("cancel_url")), "optional": True},
        ]
        return {
            "valid": provider in {"local", "processor", "stripe"} and not missing,
            "provider": "stripe-shell" if provider == "stripe" else provider,
            "missing": missing,
            "status": "stubbed" if provider == "stripe" else "local_stub",
            "mode": "live-ready" if provider == "stripe" else "stub",
            "checklist": checklist,
            "setup_instructions": "Set Stripe keys and webhook signing secret. Verify webhook signatures before accepting live payment events.",
        }

    def link(
        self,
        tenant_id: str,
        invoice: dict[str, object],
        idempotency_key: str | None = None,
        options: dict[str, object] | None = None,
    ) -> ProviderResult:
        options = options or {}
        invoice_id = str(invoice.get("invoice_id", "invoice"))
        key = idempotency_key or invoice_id
        reference_id = stable_id("payment-link", tenant_id, key)
        provider_reference_id = stable_id("provider-payment", tenant_id, invoice_id)
        provider = str(options.get("provider", "local"))
        provider_name = "stripe-shell" if provider == "stripe" else "local-payment"
        base_url = "https://pay.stripe.local" if provider == "stripe" else "https://payments.local"
        return ProviderResult(
            provider=provider_name,
            status="created",
            reference_id=reference_id,
            payload={
                "invoice_id": invoice_id,
                "idempotency_key": key,
                "provider_reference_id": provider_reference_id,
                "payment_url": f"{base_url}/{tenant_id}/{invoice_id}?ref={provider_reference_id}",
                "invoice_association": invoice_id,
                "webhook_signature_validation": "placeholder",
            },
        )

    def status(
        self,
        tenant_id: str,
        invoice_id: str,
        status: str,
        provider_reference_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ProviderResult:
        if status not in self.valid_statuses:
            raise ValueError("unsupported payment status")
        key = idempotency_key or f"{invoice_id}:{status}:{provider_reference_id or 'local'}"
        return ProviderResult(
            provider="local-payment",
            status="updated",
            reference_id=stable_id("payment-status", tenant_id, key),
            payload={
                "invoice_id": invoice_id,
                "payment_status": status,
                "provider_reference_id": provider_reference_id or stable_id("provider-payment", tenant_id, invoice_id),
                "idempotency_key": key,
                "received_at": utc_now(),
            },
        )

    def map_webhook_status(self, payload: dict[str, object]) -> str:
        explicit_status = str(payload.get("status", "") or "")
        if explicit_status in self.valid_statuses:
            return explicit_status
        event_type = str(payload.get("event_type", "") or payload.get("type", ""))
        return self.provider_status_map.get(event_type, "pending")

    def validate_webhook(self, payload: dict[str, object]) -> dict[str, object]:
        if payload.get("signature_valid") is False:
            return {"valid": False, "failure_reason": "payment webhook signature rejected"}
        return {
            "valid": True,
            "provider": "stripe-shell" if payload.get("provider") == "stripe" else "local-payment",
            "signature_validation": "placeholder",
        }


def _as_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]
