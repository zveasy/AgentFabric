"""Federation orchestration service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from agentfabric.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore
from veil_client import AuditEventRequest, PolicyCheckRequest, VeilClient

from .capability_exchange import CapabilityExchange
from .federated_directory import FederatedDirectory
from .federated_org import FederatedOrg
from .federation_policy import FederationPolicy
from .federation_registry import FederationRegistry
from .messaging import FederatedMessage, FederatedMessageRouter, FederatedReceipt
from .remote_agent import RemoteAgent
from .trust_agreement import TrustAgreement


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class RemoteDelegation:
    tenant_id: str
    organization_id: str
    trust_agreement_id: str
    remote_org_id: str
    source_agent_id: str
    destination_agent_id: str
    task_type: str
    payload: dict[str, object]
    created_by: str
    status: str = "requested"
    delegation_id: str = field(default_factory=lambda: f"fed-del-{uuid4().hex[:12]}")
    receipt_id: str | None = None
    result: dict[str, object] | None = None
    rejection_reason: str = ""
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def with_update(self, **updates: object) -> "RemoteDelegation":
        data = self.as_dict()
        data.update(updates)
        data["updated_at"] = utc_now().isoformat()
        return RemoteDelegation.from_dict(data)

    def as_dict(self) -> dict[str, object]:
        return {
            "delegation_id": self.delegation_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "trust_agreement_id": self.trust_agreement_id,
            "remote_org_id": self.remote_org_id,
            "source_agent_id": self.source_agent_id,
            "destination_agent_id": self.destination_agent_id,
            "task_type": self.task_type,
            "payload": dict(self.payload),
            "created_by": self.created_by,
            "status": self.status,
            "receipt_id": self.receipt_id,
            "result": dict(self.result or {}),
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "RemoteDelegation":
        return cls(
            delegation_id=str(value["delegation_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            trust_agreement_id=str(value["trust_agreement_id"]),
            remote_org_id=str(value["remote_org_id"]),
            source_agent_id=str(value["source_agent_id"]),
            destination_agent_id=str(value["destination_agent_id"]),
            task_type=str(value["task_type"]),
            payload=dict(value.get("payload", {})),
            created_by=str(value.get("created_by", "")),
            status=str(value.get("status", "requested")),
            receipt_id=str(value["receipt_id"]) if value.get("receipt_id") else None,
            result=dict(value.get("result", {})) or None,
            rejection_reason=str(value.get("rejection_reason", "")),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
            updated_at=datetime.fromisoformat(str(value["updated_at"])) if value.get("updated_at") else utc_now(),
        )


class FederationService:
    def __init__(self, *, persistence: PersistenceStore, event_store: EventStore, veil_client: VeilClient) -> None:
        self.persistence = persistence
        self.event_store = event_store
        self.veil_client = veil_client
        self.registry = FederationRegistry(persistence)
        self.directory = FederatedDirectory(persistence, CapabilityExchange(veil_client))
        self.router = FederatedMessageRouter(persistence=persistence, event_store=event_store, veil_client=veil_client)

    def create_org(self, org: FederatedOrg) -> FederatedOrg:
        saved = self.registry.add_org(org)
        return saved

    def create_agreement(self, agreement: TrustAgreement) -> TrustAgreement:
        if self.registry.find_org_by_remote_id(agreement.tenant_id, agreement.remote_org_id) is None:
            raise NotFoundError("remote organization must be registered before agreement")
        saved = self.registry.put_agreement(agreement)
        self.event_store.append("federation.agreement.created", saved.agreement_id, saved.as_dict())
        return saved

    def activate_agreement(self, agreement_id: str) -> TrustAgreement:
        agreement = self.registry.get_agreement(agreement_id)
        if agreement.is_expired():
            expired = agreement.with_status("expired")
            self.registry.put_agreement(expired)
            self.event_store.append("federation.agreement.expired", agreement_id, expired.as_dict())
            raise ConflictError("trust agreement expired")
        activated = agreement.with_status("active")
        self.registry.put_agreement(activated)
        self.event_store.append("federation.agreement.activated", agreement_id, activated.as_dict())
        return activated

    def revoke_agreement(self, agreement_id: str, reason: str = "") -> TrustAgreement:
        agreement = self.registry.get_agreement(agreement_id)
        revoked = agreement.with_status("revoked", reason)
        self.registry.put_agreement(revoked)
        self.event_store.append("federation.agreement.revoked", agreement_id, revoked.as_dict())
        self.event_store.append("federation.remote_org.blocked", agreement.remote_org_id, {"tenant_id": agreement.tenant_id, "organization_id": agreement.organization_id, "remote_org_id": agreement.remote_org_id, "reason": reason})
        return revoked

    def policy(self, tenant_id: str, organization_id: str) -> FederationPolicy:
        item = self.persistence.get("federation_policies", tenant_id)
        return FederationPolicy.from_dict(item) if item else FederationPolicy(tenant_id=tenant_id, organization_id=organization_id)

    def publish_capability(self, agent: RemoteAgent, agreement: TrustAgreement) -> RemoteAgent:
        self._assert_active(agreement)
        self.directory.publish_local(agent)
        self.event_store.append("federation.capability.published", agent.catalog_id, agent.as_dict())
        return agent

    def import_capability(self, agent: RemoteAgent, agreement: TrustAgreement) -> RemoteAgent:
        self._assert_active(agreement)
        self.directory.import_remote(agent)
        self.event_store.append("federation.capability.imported", agent.catalog_id, agent.as_dict())
        return agent

    def discover(self, *, tenant_id: str, organization_id: str, agreement_id: str, capability: str | None = None) -> list[RemoteAgent]:
        agreement = self.registry.get_agreement(agreement_id)
        self._assert_active(agreement)
        return self.directory.discover(tenant_id=tenant_id, agreement=agreement, policy=self.policy(tenant_id, organization_id), capability=capability)

    def send_message(self, message: FederatedMessage, signing_secret: str) -> FederatedReceipt:
        agreement = self.registry.get_agreement(message.trust_agreement_id)
        self._assert_active(agreement)
        return self.router.send(message, agreement=agreement, signing_secret=signing_secret)

    def get_message(self, message_id: str) -> FederatedMessage:
        item = self.persistence.get("federation_messages", message_id)
        if item is None:
            raise NotFoundError("federated message not found")
        return FederatedMessage.from_dict(item)

    def add_receipt(self, message_id: str, tenant_id: str, status: str, reason: str = "") -> FederatedReceipt:
        receipt = self.router.receipt(message_id, tenant_id, status, reason)
        self.persistence.put("federation_receipts", receipt.receipt_id, receipt.as_dict())
        return receipt

    def request_delegation(self, delegation: RemoteDelegation, *, signing_secret: str, governance_approved: bool) -> RemoteDelegation:
        agreement = self.registry.get_agreement(delegation.trust_agreement_id)
        self._assert_active(agreement)
        if delegation.task_type not in agreement.allowed_capabilities:
            raise AuthorizationError("delegation capability is not allowed by agreement")
        if delegation.task_type in {"code_review", "compliance_review", "package_verification"} and not governance_approved:
            raise AuthorizationError("governance approval is required for delegation")
        self._safe_payload(delegation.payload)
        response = self.veil_client.check_policy(
            PolicyCheckRequest(agent_id=delegation.source_agent_id, action=f"federation.delegate.{delegation.task_type}", payload=delegation.as_dict())
        )
        if not response.allowed:
            raise AuthorizationError(response.reason or "VEIL policy denied federation delegation")
        message = FederatedMessage.create(
            signing_secret=signing_secret,
            source_org_id=delegation.organization_id,
            source_tenant_id=delegation.tenant_id,
            destination_org_id=delegation.remote_org_id,
            destination_tenant_id=delegation.remote_org_id,
            source_agent_id=delegation.source_agent_id,
            destination_agent_id=delegation.destination_agent_id,
            trust_agreement_id=delegation.trust_agreement_id,
            payload={"delegation_id": delegation.delegation_id, "task_type": delegation.task_type, **delegation.payload},
            veil_reference=str(delegation.payload.get("veil_reference", "veil-ref")),
        )
        receipt = self.send_message(message, signing_secret)
        requested = delegation.with_update(receipt_id=receipt.receipt_id)
        self.persistence.put("federation_delegations", requested.delegation_id, requested.as_dict())
        self.event_store.append("federation.delegation.requested", requested.delegation_id, requested.as_dict())
        return requested

    def complete_delegation(self, delegation_id: str, result: dict[str, object]) -> RemoteDelegation:
        delegation = self.get_delegation(delegation_id)
        completed = delegation.with_update(status="completed", result=result)
        self.persistence.put("federation_delegations", delegation_id, completed.as_dict())
        self.event_store.append("federation.delegation.completed", delegation_id, completed.as_dict())
        self.veil_client.create_audit_event(AuditEventRequest(agent_id=completed.destination_agent_id, event_type="federation.delegation.completed", payload=completed.as_dict()))
        return completed

    def reject_delegation(self, delegation_id: str, reason: str) -> RemoteDelegation:
        delegation = self.get_delegation(delegation_id)
        rejected = delegation.with_update(status="failed", rejection_reason=reason)
        self.persistence.put("federation_delegations", delegation_id, rejected.as_dict())
        self.event_store.append("federation.delegation.failed", delegation_id, rejected.as_dict())
        return rejected

    def get_delegation(self, delegation_id: str) -> RemoteDelegation:
        item = self.persistence.get("federation_delegations", delegation_id)
        if item is None:
            raise NotFoundError("federation delegation not found")
        return RemoteDelegation.from_dict(item)

    def reputation(self, tenant_id: str, remote_org_id: str) -> dict[str, object]:
        delegations = [RemoteDelegation.from_dict(item) for item in self.persistence.list_tenant("federation_delegations", tenant_id) if item.get("remote_org_id") == remote_org_id]
        messages = [item for item in self.persistence.list_tenant("federation_messages", tenant_id) if item.get("destination_org_id") == remote_org_id]
        completed = sum(1 for item in delegations if item.status == "completed")
        failed = sum(1 for item in delegations if item.status == "failed")
        rejected = sum(1 for item in messages if item.get("status") == "rejected")
        total = max(completed + failed, 1)
        reliability = completed / total
        rejection_penalty = min(rejected / max(len(messages), 1), 0.5)
        score = round(max(0.0, reliability - rejection_penalty), 4)
        return {
            "tenant_id": tenant_id,
            "remote_org_id": remote_org_id,
            "remote_task_success_rate": reliability,
            "remote_failure_rate": failed / total,
            "message_rejection_rate": rejection_penalty,
            "federated_reputation_score": score,
            "partner_reliability_score": score,
            "remote_agent_confidence_score": round(score * min((completed + failed) / 10, 1.0), 4),
        }

    def _assert_active(self, agreement: TrustAgreement) -> None:
        if agreement.is_expired():
            expired = agreement.with_status("expired")
            self.registry.put_agreement(expired)
            self.event_store.append("federation.agreement.expired", agreement.agreement_id, expired.as_dict())
            raise AuthorizationError("trust agreement expired")
        if not agreement.is_active():
            raise AuthorizationError("active trust agreement is required")

    def _safe_payload(self, payload: dict[str, object]) -> None:
        if any(str(key).lower() in {"secret", "raw", "password", "token_value"} for key in payload):
            raise ValidationError("raw sensitive federation payload values are not allowed")
