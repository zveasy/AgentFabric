"""Private marketplace tenancy isolation."""

from __future__ import annotations

from collections import defaultdict

from agentfabric.errors import AuthorizationError, ConflictError, NotFoundError


class PrivateMarketplaceService:
    """Manages isolated namespaces for enterprise tenants."""

    def __init__(self) -> None:
        self._namespace_owner: dict[str, str] = {}
        self._memberships: defaultdict[str, set[str]] = defaultdict(set)

    def create_namespace(self, tenant_id: str, namespace: str) -> None:
        if namespace in self._namespace_owner:
            raise ConflictError("namespace already exists")
        self._namespace_owner[namespace] = tenant_id
        self._memberships[namespace].add(tenant_id)

    def grant_access(self, owner_tenant_id: str, namespace: str, target_tenant_id: str) -> None:
        owner = self._namespace_owner.get(namespace)
        if owner is None:
            raise NotFoundError("namespace not found")
        if owner != owner_tenant_id:
            raise AuthorizationError("only namespace owner can grant access")
        self._memberships[namespace].add(target_tenant_id)

    def check_access(self, tenant_id: str, namespace: str) -> None:
        if namespace not in self._namespace_owner:
            raise NotFoundError("namespace not found")
        if tenant_id not in self._memberships[namespace]:
            raise AuthorizationError("tenant has no access to private namespace")
