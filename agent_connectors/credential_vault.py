"""Tenant-isolated credential reference vault."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from agentfabric.errors import AuthorizationError, NotFoundError
from agentfabric.persistence import PersistenceStore


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class CredentialReference:
    tenant_id: str
    connector_id: str
    credential_type: str
    created_by: str
    credential_id: str = field(default_factory=lambda: f"credential-{uuid4().hex[:12]}")
    version: int = 1
    status: str = "active"
    created_at: datetime = field(default_factory=utc_now)
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None

    @property
    def reference_id(self) -> str:
        return f"vault-ref:{self.credential_id}:v{self.version}"

    def rotate(self) -> "CredentialReference":
        return replace(self, version=self.version + 1, status="active", rotated_at=utc_now())

    def revoke(self) -> "CredentialReference":
        return replace(self, status="revoked", revoked_at=utc_now())

    def as_dict(self) -> dict[str, object]:
        return {
            "credential_id": self.credential_id,
            "credential_ref": self.reference_id,
            "tenant_id": self.tenant_id,
            "connector_id": self.connector_id,
            "credential_type": self.credential_type,
            "created_by": self.created_by,
            "version": self.version,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "rotated_at": self.rotated_at.isoformat() if self.rotated_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "CredentialReference":
        return cls(
            credential_id=str(value["credential_id"]),
            tenant_id=str(value["tenant_id"]),
            connector_id=str(value["connector_id"]),
            credential_type=str(value["credential_type"]),
            created_by=str(value.get("created_by", "")),
            version=int(value.get("version", 1)),
            status=str(value.get("status", "active")),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
            rotated_at=datetime.fromisoformat(str(value["rotated_at"])) if value.get("rotated_at") else None,
            revoked_at=datetime.fromisoformat(str(value["revoked_at"])) if value.get("revoked_at") else None,
        )


class ProductionCredentialBackend(Protocol):
    def put(self, reference: CredentialReference, secret: str) -> None: ...

    def get(self, reference: CredentialReference) -> str: ...

    def delete(self, reference: CredentialReference) -> None: ...


class CredentialVault:
    def __init__(self, persistence: PersistenceStore, backend: ProductionCredentialBackend | None = None) -> None:
        self.persistence = persistence
        self.backend = backend
        self._local_secrets: dict[str, str] = {}
        self.persistence.initialize()

    def create(
        self,
        *,
        tenant_id: str,
        connector_id: str,
        credential_type: str,
        created_by: str,
        secret: str,
    ) -> CredentialReference:
        if not secret:
            raise ValueError("credential secret is required")
        reference = CredentialReference(tenant_id, connector_id, credential_type, created_by)
        self._store_secret(reference, secret)
        self.persistence.put("connector_credentials", reference.credential_id, reference.as_dict())
        return reference

    def get(self, tenant_id: str, credential_id: str) -> CredentialReference:
        value = self.persistence.get("connector_credentials", credential_id)
        if value is None:
            raise NotFoundError("credential not found")
        reference = CredentialReference.from_dict(value)
        if reference.tenant_id != tenant_id:
            raise AuthorizationError("cross-tenant credential access denied")
        return reference

    def resolve(self, tenant_id: str, credential_id: str) -> str:
        reference = self.get(tenant_id, credential_id)
        if reference.status != "active":
            raise AuthorizationError("credential is not active")
        if self.backend:
            return self.backend.get(reference)
        try:
            return self._local_secrets[reference.credential_id]
        except KeyError as exc:
            raise NotFoundError("credential material unavailable") from exc

    def rotate(self, tenant_id: str, credential_id: str, secret: str) -> CredentialReference:
        reference = self.get(tenant_id, credential_id).rotate()
        self._store_secret(reference, secret)
        self.persistence.put("connector_credentials", credential_id, reference.as_dict())
        return reference

    def revoke(self, tenant_id: str, credential_id: str) -> CredentialReference:
        reference = self.get(tenant_id, credential_id).revoke()
        if self.backend:
            self.backend.delete(reference)
        else:
            self._local_secrets.pop(reference.credential_id, None)
        self.persistence.put("connector_credentials", credential_id, reference.as_dict())
        return reference

    def _store_secret(self, reference: CredentialReference, secret: str) -> None:
        if self.backend:
            self.backend.put(reference, secret)
        else:
            self._local_secrets[reference.credential_id] = secret
