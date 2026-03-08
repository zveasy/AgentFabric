"""JWT auth service and FastAPI middleware helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Iterable
from uuid import uuid4

import jwt
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentfabric.server.config import Settings
from agentfabric.server.models import Principal, Token


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _coerce_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class AuthPrincipal:
    principal_id: str
    tenant_id: str
    scopes: tuple[str, ...]
    principal_type: str
    token_id: str


class AuthService:
    """JWT issuer + token persistence validation."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def register_principal(self, db: Session, *, principal_id: str, tenant_id: str, principal_type: str, scopes: list[str], role: str = "viewer") -> Principal:
        from agentfabric.phase4.rbac import RbacService
        role_perms = set(RbacService.ROLE_PERMISSIONS.get(role, []))
        effective_scopes = sorted(set(scopes) | role_perms)
        existing = db.get(Principal, principal_id)
        if existing:
            existing.tenant_id = tenant_id
            existing.principal_type = principal_type
            existing.role = role
            existing.scopes_csv = ",".join(effective_scopes)
            db.add(existing)
            db.flush()
            return existing
        principal = Principal(
            principal_id=principal_id,
            tenant_id=tenant_id,
            principal_type=principal_type,
            role=role,
            scopes_csv=",".join(effective_scopes),
        )
        db.add(principal)
        db.flush()
        return principal

    def issue_token(self, db: Session, *, principal_id: str, ttl_seconds: int) -> tuple[str, int]:
        from agentfabric.phase4.rbac import RbacService
        principal = db.get(Principal, principal_id)
        if principal is None:
            raise HTTPException(status_code=404, detail="principal not found")
        role_perms = set(RbacService.ROLE_PERMISSIONS.get(principal.role, []))
        stored_scopes = set(principal.scopes_csv.split(",")) if principal.scopes_csv else set()
        effective_scopes = sorted(stored_scopes | role_perms)
        token_id = uuid4().hex
        expires_at = utc_now() + timedelta(seconds=ttl_seconds)
        claims = {
            "sub": principal.principal_id,
            "tid": principal.tenant_id,
            "scp": effective_scopes,
            "pty": principal.principal_type,
            "jti": token_id,
            "exp": int(expires_at.timestamp()),
            "iat": int(utc_now().timestamp()),
        }
        encoded = jwt.encode(claims, self.settings.jwt_secret, algorithm=self.settings.jwt_algorithm)
        token_hash = sha256(encoded.encode("utf-8")).hexdigest()
        db.add(
            Token(
                token_id=token_id,
                principal_id=principal.principal_id,
                token_hash=token_hash,
                expires_at=expires_at,
                revoked=False,
            )
        )
        db.flush()
        return encoded, ttl_seconds

    def rotate_token(self, db: Session, *, bearer_token: str, ttl_seconds: int) -> tuple[str, int]:
        principal = self.authenticate(db, bearer_token)
        token_row = db.get(Token, principal.token_id)
        if token_row is not None:
            token_row.revoked = True
            db.add(token_row)
        db.flush()
        return self.issue_token(db, principal_id=principal.principal_id, ttl_seconds=ttl_seconds)

    def authenticate(self, db: Session, bearer_token: str) -> AuthPrincipal:
        try:
            decoded = jwt.decode(
                bearer_token,
                self.settings.jwt_secret,
                algorithms=[self.settings.jwt_algorithm],
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc
        token_id = decoded.get("jti")
        if not token_id:
            raise HTTPException(status_code=401, detail="missing token id")
        token = db.get(Token, token_id)
        if token is None:
            raise HTTPException(status_code=401, detail="token not found")
        if token.revoked:
            raise HTTPException(status_code=401, detail="token revoked")
        if _coerce_utc(token.expires_at) <= utc_now():
            raise HTTPException(status_code=401, detail="token expired")
        expected_hash = sha256(bearer_token.encode("utf-8")).hexdigest()
        if token.token_hash != expected_hash:
            raise HTTPException(status_code=401, detail="token hash mismatch")
        principal = db.get(Principal, decoded["sub"])
        if principal is None:
            raise HTTPException(status_code=401, detail="principal not found")
        scopes = tuple(sorted(set(decoded.get("scp", []))))
        return AuthPrincipal(
            principal_id=principal.principal_id,
            tenant_id=principal.tenant_id,
            scopes=scopes,
            principal_type=principal.principal_type,
            token_id=token_id,
        )

    @staticmethod
    def parse_bearer_header(value: str | None) -> str:
        if not value:
            raise HTTPException(status_code=401, detail="missing Authorization header")
        prefix = "Bearer "
        if not value.startswith(prefix):
            raise HTTPException(status_code=401, detail="Authorization must use Bearer token")
        return value[len(prefix) :]


def require_scopes(request: Request, scopes: Iterable[str], tenant_id: str | None = None) -> AuthPrincipal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=401, detail="missing authenticated principal")
    required = set(scopes)
    if required and not required.issubset(set(principal.scopes)):
        raise HTTPException(status_code=403, detail="insufficient scope")
    if tenant_id and principal.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="cross-tenant access denied")
    return principal
