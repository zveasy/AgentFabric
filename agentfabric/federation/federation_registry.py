"""Persistence-backed federation registry."""

from __future__ import annotations

from agentfabric.errors import NotFoundError
from agentfabric.persistence import PersistenceStore

from .federated_org import FederatedOrg
from .trust_agreement import TrustAgreement


class FederationRegistry:
    def __init__(self, persistence: PersistenceStore) -> None:
        self.persistence = persistence

    def add_org(self, org: FederatedOrg) -> FederatedOrg:
        self.persistence.put("federation_orgs", org.org_id, org.as_dict())
        return org

    def list_orgs(self, tenant_id: str) -> list[FederatedOrg]:
        return [FederatedOrg.from_dict(item) for item in self.persistence.list_tenant("federation_orgs", tenant_id)]

    def get_org(self, org_id: str) -> FederatedOrg:
        item = self.persistence.get("federation_orgs", org_id)
        if item is None:
            raise NotFoundError("federated org not found")
        return FederatedOrg.from_dict(item)

    def find_org_by_remote_id(self, tenant_id: str, remote_org_id: str) -> FederatedOrg | None:
        for org in self.list_orgs(tenant_id):
            if org.remote_org_id == remote_org_id:
                return org
        return None

    def put_agreement(self, agreement: TrustAgreement) -> TrustAgreement:
        self.persistence.put("federation_agreements", agreement.agreement_id, agreement.as_dict())
        return agreement

    def list_agreements(self, tenant_id: str) -> list[TrustAgreement]:
        return [TrustAgreement.from_dict(item) for item in self.persistence.list_tenant("federation_agreements", tenant_id)]

    def get_agreement(self, agreement_id: str) -> TrustAgreement:
        item = self.persistence.get("federation_agreements", agreement_id)
        if item is None:
            raise NotFoundError("trust agreement not found")
        return TrustAgreement.from_dict(item)

    def active_for_remote(self, tenant_id: str, remote_org_id: str) -> TrustAgreement | None:
        for agreement in self.list_agreements(tenant_id):
            if agreement.remote_org_id == remote_org_id and agreement.is_active():
                return agreement
        return None
