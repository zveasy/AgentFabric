"""Federated capability import/export."""

from __future__ import annotations

from agentfabric.errors import AuthorizationError
from veil_client import PolicyCheckRequest, VeilClient

from .federation_policy import FederationPolicy
from .remote_agent import RemoteAgent
from .trust_agreement import TrustAgreement


class CapabilityExchange:
    def __init__(self, veil_client: VeilClient) -> None:
        self.veil_client = veil_client

    def filter_catalog(self, *, agreement: TrustAgreement, policy: FederationPolicy, agents: list[RemoteAgent]) -> list[RemoteAgent]:
        if not agreement.is_active():
            raise AuthorizationError("active trust agreement is required")
        visible: list[RemoteAgent] = []
        for agent in agents:
            if agent.remote_org_id in policy.blocked_remote_orgs or agent.remote_agent_id in policy.blocked_remote_agents:
                continue
            if agent.publisher_id and agent.publisher_id in policy.blocked_publishers:
                continue
            if agent.reputation_score < policy.min_reputation_score or agent.blocked:
                continue
            capabilities = [
                cap for cap in agent.capabilities
                if cap.package_signature_verified
                and agreement.allows_capability(cap.name)
                and policy.allows_capability(cap.name)
                and set(cap.data_classes).issubset(set(agreement.permitted_data_classes))
                and set(cap.data_classes).issubset(set(policy.permitted_data_classes))
            ]
            if not capabilities:
                continue
            response = self.veil_client.check_policy(
                PolicyCheckRequest(
                    agent_id=agent.remote_agent_id,
                    action="federation.discovery",
                    payload={"tenant_id": agent.tenant_id, "remote_org_id": agent.remote_org_id, "capabilities": [cap.name for cap in capabilities]},
                )
            )
            if response.allowed:
                visible.append(
                    RemoteAgent(
                        catalog_id=agent.catalog_id,
                        tenant_id=agent.tenant_id,
                        organization_id=agent.organization_id,
                        remote_org_id=agent.remote_org_id,
                        remote_agent_id=agent.remote_agent_id,
                        name=agent.name,
                        capabilities=tuple(capabilities),
                        reputation_score=agent.reputation_score,
                        publisher_id=agent.publisher_id,
                        blocked=agent.blocked,
                        imported_at=agent.imported_at,
                    )
                )
        return visible
