"""Federated message routing with replay and TTL protection."""

from __future__ import annotations

from agentfabric.errors import AuthorizationError, ValidationError
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore
from veil_client import PolicyCheckRequest, VeilClient

from ..trust_agreement import TrustAgreement
from .federated_message import FederatedMessage
from .federated_receipt import FederatedReceipt
from .remote_delivery import RemoteDelivery


class FederatedMessageRouter:
    def __init__(self, *, persistence: PersistenceStore, event_store: EventStore, veil_client: VeilClient, delivery: RemoteDelivery | None = None) -> None:
        self.persistence = persistence
        self.event_store = event_store
        self.veil_client = veil_client
        self.delivery = delivery or RemoteDelivery()

    def send(self, message: FederatedMessage, *, agreement: TrustAgreement, signing_secret: str) -> FederatedReceipt:
        self._validate(message, agreement=agreement, signing_secret=signing_secret)
        self.persistence.put("federation_messages", message.message_id, message.as_dict())
        self.persistence.put("federation_nonces", message.nonce, {"tenant_id": message.source_tenant_id, "nonce": message.nonce, "message_id": message.message_id})
        self.event_store.append("federation.message.sent", message.message_id, {"tenant_id": message.source_tenant_id, "organization_id": message.source_org_id, **message.as_dict()})
        receipt = self.delivery.deliver(message)
        self.persistence.put("federation_receipts", receipt.receipt_id, receipt.as_dict())
        return receipt

    def receive(self, message: FederatedMessage, *, agreement: TrustAgreement, signing_secret: str) -> FederatedReceipt:
        self._validate(message, agreement=agreement, signing_secret=signing_secret)
        receipt = FederatedReceipt(message_id=message.message_id, tenant_id=message.destination_tenant_id, status="received")
        self.persistence.put("federation_messages", message.message_id, message.as_dict())
        self.persistence.put("federation_receipts", receipt.receipt_id, receipt.as_dict())
        self.persistence.put("federation_nonces", message.nonce, {"tenant_id": message.destination_tenant_id, "nonce": message.nonce, "message_id": message.message_id})
        self.event_store.append("federation.message.received", message.message_id, {"tenant_id": message.destination_tenant_id, "organization_id": message.destination_org_id, **message.as_dict()})
        return receipt

    def receipt(self, message_id: str, tenant_id: str, status: str, reason: str = "") -> FederatedReceipt:
        receipt = FederatedReceipt(message_id=message_id, tenant_id=tenant_id, status=status, reason=reason)
        self.persistence.put("federation_receipts", receipt.receipt_id, receipt.as_dict())
        return receipt

    def _validate(self, message: FederatedMessage, *, agreement: TrustAgreement, signing_secret: str) -> None:
        if not agreement.is_active():
            raise AuthorizationError("active trust agreement is required")
        if message.expired():
            self.event_store.append("federation.message.rejected", message.message_id, {"tenant_id": message.source_tenant_id, "reason": "message expired"})
            raise ValidationError("message expired")
        if self.persistence.get("federation_nonces", message.nonce):
            self.event_store.append("federation.message.rejected", message.message_id, {"tenant_id": message.source_tenant_id, "reason": "replay detected"})
            raise ValidationError("replayed message rejected")
        if not message.signature or not message.verify(signing_secret):
            self.event_store.append("federation.remote_key.rejected", message.message_id, {"tenant_id": message.source_tenant_id, "reason": "bad signature"})
            raise AuthorizationError("invalid federated message signature")
        if any(str(key).lower() in {"secret", "raw", "password", "token_value"} for key in message.payload):
            raise ValidationError("raw sensitive federated payload values are not allowed")
        response = self.veil_client.check_policy(
            PolicyCheckRequest(agent_id=message.source_agent_id, action="federation.message", payload=message.as_dict())
        )
        if not response.allowed:
            self.event_store.append("federation.message.rejected", message.message_id, {"tenant_id": message.source_tenant_id, "reason": response.reason})
            raise AuthorizationError(response.reason or "VEIL policy denied federated message")
