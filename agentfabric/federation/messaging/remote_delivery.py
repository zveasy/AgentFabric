"""Remote delivery adapter."""

from __future__ import annotations

from .federated_message import FederatedMessage
from .federated_receipt import FederatedReceipt


class RemoteDelivery:
    def deliver(self, message: FederatedMessage) -> FederatedReceipt:
        return FederatedReceipt(message_id=message.message_id, tenant_id=message.source_tenant_id, status="accepted")
