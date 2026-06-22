"""Tenant-scoped repository lifecycle management."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256

from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError, NotFoundError
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore
from agentfabric.repository_factory import RepositoryBlueprint, RepositoryManifest


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class RepositoryRecord:
    repository_id: str
    tenant_id: str
    organization_id: str
    name: str
    version: str
    status: str
    manifest: dict[str, object]
    blueprint_digest: str
    owner: str
    dependencies: tuple[str, ...] = ()
    parent_repository_id: str | None = None
    lineage_action: str = "create"
    release_history: tuple[str, ...] = ("1.0.0",)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "repository_id": self.repository_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "manifest": dict(self.manifest),
            "blueprint_digest": self.blueprint_digest,
            "owner": self.owner,
            "dependencies": sorted(self.dependencies),
            "parent_repository_id": self.parent_repository_id,
            "lineage_action": self.lineage_action,
            "release_history": list(self.release_history),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "RepositoryRecord":
        return cls(
            repository_id=str(value["repository_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            name=str(value["name"]),
            version=str(value["version"]),
            status=str(value["status"]),
            manifest=dict(value["manifest"]),
            blueprint_digest=str(value["blueprint_digest"]),
            owner=str(value["owner"]),
            dependencies=tuple(str(item) for item in value.get("dependencies", ())),
            parent_repository_id=str(value["parent_repository_id"]) if value.get("parent_repository_id") else None,
            lineage_action=str(value.get("lineage_action", "create")),
            release_history=tuple(str(item) for item in value.get("release_history", ("1.0.0",))),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            updated_at=datetime.fromisoformat(str(value["updated_at"])),
        )


class RepositoryLifecycleService:
    def __init__(self, persistence: PersistenceStore, event_store: EventStore) -> None:
        self.persistence = persistence
        self.event_store = event_store
        self.persistence.initialize()

    def create(self, ctx: TenantContext, blueprint: RepositoryBlueprint) -> RepositoryRecord:
        record = RepositoryRecord(
            repository_id=blueprint.manifest.repository_id,
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
            name=blueprint.manifest.name,
            version="1.0.0",
            status="active",
            manifest=blueprint.manifest.as_dict(),
            blueprint_digest=blueprint.digest,
            owner=ctx.principal_id,
            dependencies=blueprint.manifest.dependencies,
        )
        self._save(record, "factory.repository.created")
        return record

    def get(self, ctx: TenantContext, repository_id: str) -> RepositoryRecord:
        value = self.persistence.get("factory_repositories", repository_id)
        if value is None:
            raise NotFoundError("repository not found")
        record = RepositoryRecord.from_dict(value)
        if record.tenant_id != ctx.tenant_id and not ctx.is_global_admin:
            raise AuthorizationError("cross-tenant repository access denied")
        return record

    def list(self, ctx: TenantContext) -> list[RepositoryRecord]:
        return [RepositoryRecord.from_dict(item) for item in self.persistence.list_tenant("factory_repositories", ctx.tenant_id)]

    def update(self, ctx: TenantContext, repository_id: str, manifest: RepositoryManifest, version: str) -> RepositoryRecord:
        current = self.get(ctx, repository_id)
        updated = replace(
            current,
            version=version,
            manifest=manifest.as_dict(),
            dependencies=manifest.dependencies,
            release_history=(*current.release_history, version),
            updated_at=utc_now(),
        )
        self._save(updated, "factory.repository.updated")
        return updated

    def deprecate(self, ctx: TenantContext, repository_id: str) -> RepositoryRecord:
        return self._status(ctx, repository_id, "deprecated", "factory.repository.deprecated")

    def archive(self, ctx: TenantContext, repository_id: str) -> RepositoryRecord:
        return self._status(ctx, repository_id, "archived", "factory.repository.archived")

    def restore(self, ctx: TenantContext, repository_id: str) -> RepositoryRecord:
        return self._status(ctx, repository_id, "active", "factory.repository.restored")

    def clone(self, ctx: TenantContext, repository_id: str, name: str) -> RepositoryRecord:
        return self._derive(ctx, repository_id, name, "clone")

    def fork(self, ctx: TenantContext, repository_id: str, name: str) -> RepositoryRecord:
        return self._derive(ctx, repository_id, name, "fork")

    def _derive(self, ctx: TenantContext, repository_id: str, name: str, action: str) -> RepositoryRecord:
        parent = self.get(ctx, repository_id)
        manifest = RepositoryManifest.from_dict({**parent.manifest, "name": name})
        derived_id = f"repo-{sha256(f'{parent.repository_id}:{action}:{name}'.encode()).hexdigest()[:16]}"
        record = replace(
            parent,
            repository_id=derived_id,
            name=name,
            manifest=manifest.as_dict(),
            parent_repository_id=parent.repository_id,
            lineage_action=action,
            owner=ctx.principal_id,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        event_type = {
            "clone": "factory.repository.cloned",
            "fork": "factory.repository.forked",
        }[action]
        self._save(record, event_type)
        return record

    def _status(self, ctx: TenantContext, repository_id: str, status: str, event_type: str) -> RepositoryRecord:
        record = replace(self.get(ctx, repository_id), status=status, updated_at=utc_now())
        self._save(record, event_type)
        return record

    def _save(self, record: RepositoryRecord, event_type: str) -> None:
        self.persistence.put("factory_repositories", record.repository_id, record.as_dict())
        self.event_store.append(event_type, record.repository_id, record.as_dict())
