"""Data models for registry/discovery/reviews/billing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def compute_payload_digest(payload: bytes) -> str:
    return sha256(payload).hexdigest()


@dataclass(frozen=True)
class AgentPackage:
    package_id: str
    version: str
    developer_id: str
    namespace: str
    category: str
    permissions: tuple[str, ...]
    manifest: dict[str, Any]
    payload_digest: str
    signature: str
    created_at: datetime = field(default_factory=utc_now)

    @property
    def fqid(self) -> str:
        return f"{self.namespace}/{self.package_id}:{self.version}"


@dataclass(frozen=True)
class PackageUpload:
    package_id: str
    version: str
    namespace: str
    category: str
    permissions: tuple[str, ...]
    manifest: dict[str, Any]
    payload: bytes
    signature: str


@dataclass(frozen=True)
class InstallRecord:
    tenant_id: str
    user_id: str
    package_fqid: str
    installed_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class Rating:
    tenant_id: str
    package_fqid: str
    user_id: str
    stars: int
    review: str
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class MeterEvent:
    event_type: str
    tenant_id: str
    actor_id: str
    package_fqid: str
    idempotency_key: str
    created_at: datetime = field(default_factory=utc_now)
