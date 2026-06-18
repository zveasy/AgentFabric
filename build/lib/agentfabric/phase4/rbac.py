"""Enterprise RBAC service."""

from __future__ import annotations

from collections import defaultdict

from agentfabric.errors import AuthorizationError


class RbacService:
    """Role-based authorization for runtime/registry/billing actions."""

    ROLE_PERMISSIONS = {
        "admin": {
            "registry.publish",
            "registry.install",
            "registry.read",
            "registry.read_private",
            "billing.read",
            "billing.write",
            "runtime.run",
            "audit.read",
            "audit.write",
            "audit.export",
            "rbac.assign_role",
        },
        "developer": {
            "registry.publish",
            "registry.install",
            "registry.read",
            "registry.read_private",
            "runtime.run",
            "audit.read",
        },
        "viewer": {
            "registry.install",
            "billing.read",
            "audit.read",
        },
    }

    def __init__(self) -> None:
        self._roles_by_principal: defaultdict[str, set[str]] = defaultdict(set)

    def assign_role(self, principal_id: str, role: str) -> None:
        if role not in self.ROLE_PERMISSIONS:
            raise AuthorizationError(f"unknown role: {role}")
        self._roles_by_principal[principal_id].add(role)

    def check(self, principal_id: str, permission: str) -> None:
        for role in self._roles_by_principal[principal_id]:
            if permission in self.ROLE_PERMISSIONS[role]:
                return
        raise AuthorizationError(f"principal {principal_id} lacks {permission}")
