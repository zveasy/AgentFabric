"""Developer/user authentication utilities."""

from __future__ import annotations

from dataclasses import dataclass

from agentfabric.errors import AuthorizationError, ConflictError


@dataclass(frozen=True)
class Principal:
    principal_id: str
    tenant_id: str
    principal_type: str


class ApiKeyAuthService:
    """Simple API-key auth model for hosted publishing/install."""

    def __init__(self) -> None:
        self._keys: dict[str, Principal] = {}

    def register_key(self, api_key: str, principal: Principal) -> None:
        if api_key in self._keys:
            raise ConflictError("api key already registered")
        self._keys[api_key] = principal

    def authenticate(self, api_key: str) -> Principal:
        principal = self._keys.get(api_key)
        if principal is None:
            raise AuthorizationError("invalid api key")
        return principal
