"""In-memory mesh bus with VEIL-mediated trust boundary."""

from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from typing import Callable

from agentfabric.errors import AuthorizationError, NotFoundError
from veil_client import AuditEventRequest, PolicyCheckRequest, SanitizeContextRequest, TokenIssueRequest, VeilClient

from .agent_directory import AgentDirectory
from .message import MeshMessage, MessageType

Subscriber = Callable[[MeshMessage], None]


class MessageBus:
    def __init__(self, *, directory: AgentDirectory, veil_client: VeilClient, tenant_id: str = "default") -> None:
        self.directory = directory
        self.veil_client = veil_client
        self.tenant_id = tenant_id
        self._messages: list[MeshMessage] = []
        self._subscribers: defaultdict[str, list[Subscriber]] = defaultdict(list)

    def send(self, message: MeshMessage) -> MeshMessage:
        if message.destination_agent and self.directory.get(message.destination_agent) is None:
            raise NotFoundError(f"destination agent not found: {message.destination_agent}")
        secured = self._secure_exchange(message)
        self._messages.append(secured)
        for callback in self._subscribers.get(secured.destination_agent or "*", []):
            callback(secured)
        return secured

    def broadcast(self, message: MeshMessage) -> list[MeshMessage]:
        sent: list[MeshMessage] = []
        for entry in self.directory.list_agents():
            if entry.identity.agent_id == message.source_agent:
                continue
            sent.append(
                self.send(
                    MeshMessage(
                        source_agent=message.source_agent,
                        destination_agent=entry.identity.agent_id,
                        payload=message.payload,
                        message_type=MessageType.BROADCAST.value,
                        correlation_id=message.correlation_id,
                        task_id=message.task_id,
                    )
                )
            )
        return sent

    def publish(self, topic: str, message: MeshMessage) -> MeshMessage:
        published = MeshMessage(
            source_agent=message.source_agent,
            destination_agent=topic,
            payload=message.payload,
            message_type=MessageType.PUBLISH.value,
            correlation_id=message.correlation_id,
            task_id=message.task_id,
        )
        secured = self._secure_exchange(published)
        self._messages.append(secured)
        for callback in self._subscribers.get(topic, []):
            callback(secured)
        return secured

    def subscribe(self, topic: str, callback: Subscriber) -> None:
        self._subscribers[topic].append(callback)

    def delegate_task(self, message: MeshMessage) -> MeshMessage:
        return self.send(
            MeshMessage(
                source_agent=message.source_agent,
                destination_agent=message.destination_agent,
                payload=message.payload,
                message_type=MessageType.DELEGATE.value,
                correlation_id=message.correlation_id,
                task_id=message.task_id,
            )
        )

    def history(self, *, correlation_id: str | None = None) -> list[MeshMessage]:
        if correlation_id is None:
            return list(self._messages)
        return [message for message in self._messages if message.correlation_id == correlation_id]

    def _secure_exchange(self, message: MeshMessage) -> MeshMessage:
        policy = self.veil_client.check_policy(
            PolicyCheckRequest(
                agent_id=message.source_agent,
                action=f"mesh.{message.message_type}",
                payload=message.as_dict(),
            )
        )
        if not policy.allowed:
            raise AuthorizationError(policy.reason or "VEIL policy denied mesh exchange")
        sanitized = self.veil_client.sanitize_context(
            SanitizeContextRequest(
                agent_id=message.source_agent,
                tenant_id=self.tenant_id,
                context=message.payload,
            )
        )
        token = self.veil_client.issue_agent_token(
            TokenIssueRequest(agent_id=message.source_agent, scopes=("mesh.exchange",), ttl_seconds=300)
        )
        audit = self.veil_client.create_audit_event(
            AuditEventRequest(
                agent_id=message.source_agent,
                event_type="mesh.exchange",
                payload={
                    "destination_agent": message.destination_agent,
                    "message_type": message.message_type,
                    "correlation_id": message.correlation_id,
                    "task_id": message.task_id,
                },
            )
        )
        signature = sha256(
            f"{message.source_agent}:{message.destination_agent}:{message.correlation_id}:{message.task_id}".encode(
                "utf-8"
            )
        ).hexdigest()
        trust_metadata = {
            "veil_policy_allowed": policy.allowed,
            "veil_policy_reason": policy.reason,
            "veil_redactions": list(sanitized.redactions),
            "veil_audit_event_id": audit.event_id,
            "veil_audit_accepted": audit.accepted,
            "veil_token_expires_in": token.expires_in_seconds,
        }
        return message.with_payload_and_trust(
            dict(sanitized.sanitized_context),
            trust_metadata,
            signature,
        )
