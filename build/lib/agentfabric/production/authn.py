"""Production authentication and authorization services."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from agentfabric.errors import AuthorizationError, ValidationError
from agentfabric.production.store import ProductionStore


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class TokenPrincipal:
    principal_id: str
    tenant_id: str
    principal_type: str
    scopes: tuple[str, ...]
    token_id: str


class TokenAuthService:
    """Token issuing, validation, and rotation for users/services."""

    def __init__(self, store: ProductionStore) -> None:
        self._store = store

    def register_principal(self, principal_id: str, tenant_id: str, principal_type: str, scopes: list[str]) -> None:
        self._store.upsert_principal(principal_id, tenant_id, principal_type, scopes)

    def issue_token(self, principal_id: str, ttl_seconds: int = 3600) -> str:
        principal = self._store.get_principal(principal_id)
        token_id = secrets.token_hex(12)
        secret = secrets.token_urlsafe(32)
        token = f"{token_id}.{secret}"
        token_hash = sha256(token.encode("utf-8")).hexdigest()
        expires_at = (utc_now() + timedelta(seconds=ttl_seconds)).isoformat()
        self._store.store_token(token_id, principal["principal_id"], token_hash, expires_at)
        return token

    def rotate_token(self, token: str, ttl_seconds: int = 3600) -> str:
        principal = self.authenticate_token(token)
        token_id, _ = token.split(".", 1)
        self._store.revoke_token(token_id)
        return self.issue_token(principal.principal_id, ttl_seconds=ttl_seconds)

    def authenticate_token(self, token: str, *, required_scopes: set[str] | None = None, tenant_id: str | None = None) -> TokenPrincipal:
        if "." not in token:
            raise AuthorizationError("malformed token")
        token_id, _ = token.split(".", 1)
        token_record = self._store.get_token(token_id)
        if token_record["revoked"]:
            raise AuthorizationError("token revoked")
        if datetime.fromisoformat(token_record["expires_at"]) <= utc_now():
            raise AuthorizationError("token expired")
        if token_record["token_hash"] != sha256(token.encode("utf-8")).hexdigest():
            raise AuthorizationError("invalid token secret")

        principal_record = self._store.get_principal(token_record["principal_id"])
        principal = TokenPrincipal(
            principal_id=principal_record["principal_id"],
            tenant_id=principal_record["tenant_id"],
            principal_type=principal_record["principal_type"],
            scopes=tuple(principal_record["scopes"]),
            token_id=token_id,
        )
        if required_scopes and not required_scopes.issubset(set(principal.scopes)):
            raise AuthorizationError("token scope mismatch")
        if tenant_id and principal.tenant_id != tenant_id:
            raise AuthorizationError("token tenant mismatch")
        return principal

    def register_service_identity(self, service_id: str, tenant_id: str, secret: str, scopes: list[str]) -> None:
        self._store.register_service_identity(
            service_id=service_id,
            tenant_id=tenant_id,
            secret_hash=self._store.hash_secret(secret),
            scopes=scopes,
        )

    def authenticate_service(self, service_id: str, secret: str, *, required_scopes: set[str] | None = None) -> TokenPrincipal:
        service = self._store.get_service_identity(service_id)
        if service["secret_hash"] != self._store.hash_secret(secret):
            raise AuthorizationError("invalid service credentials")
        scopes = set(service["scopes"])
        if required_scopes and not required_scopes.issubset(scopes):
            raise AuthorizationError("service scope mismatch")
        return TokenPrincipal(
            principal_id=service_id,
            tenant_id=service["tenant_id"],
            principal_type="service",
            scopes=tuple(service["scopes"]),
            token_id=f"service:{service_id}",
        )

    def require_tenant_scope(self, principal: TokenPrincipal, tenant_id: str, scope: str) -> None:
        if principal.tenant_id != tenant_id:
            raise AuthorizationError("cross-tenant access denied")
        if scope not in principal.scopes:
            raise AuthorizationError("missing required scope")

    @staticmethod
    def parse_bearer(authorization_header: str | None) -> str:
        if not authorization_header:
            raise ValidationError("missing Authorization header")
        prefix = "Bearer "
        if not authorization_header.startswith(prefix):
            raise ValidationError("Authorization must use Bearer token")
        return authorization_header[len(prefix) :]
