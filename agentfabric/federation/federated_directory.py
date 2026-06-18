"""Federated remote agent directory."""

from __future__ import annotations

from agentfabric.persistence import PersistenceStore

from .capability_exchange import CapabilityExchange
from .federation_policy import FederationPolicy
from .remote_agent import RemoteAgent
from .trust_agreement import TrustAgreement


class FederatedDirectory:
    def __init__(self, persistence: PersistenceStore, exchange: CapabilityExchange) -> None:
        self.persistence = persistence
        self.exchange = exchange

    def publish_local(self, agent: RemoteAgent) -> RemoteAgent:
        self.persistence.put("federation_remote_capabilities", agent.catalog_id, agent.as_dict())
        return agent

    def import_remote(self, agent: RemoteAgent) -> RemoteAgent:
        self.persistence.put("federation_remote_capabilities", agent.catalog_id, agent.as_dict())
        return agent

    def discover(self, *, tenant_id: str, agreement: TrustAgreement, policy: FederationPolicy, capability: str | None = None) -> list[RemoteAgent]:
        agents = [
            RemoteAgent.from_dict(item)
            for item in self.persistence.list_tenant("federation_remote_capabilities", tenant_id)
            if item.get("remote_org_id") == agreement.remote_org_id
        ]
        filtered = self.exchange.filter_catalog(agreement=agreement, policy=policy, agents=agents)
        if capability:
            return [agent for agent in filtered if any(item.name == capability for item in agent.capabilities)]
        return filtered
