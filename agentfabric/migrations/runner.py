"""Migration runner with fail-closed semantics."""

from __future__ import annotations

from datetime import datetime, timezone

from agentfabric.persistence import PersistenceStore, UnitOfWork

from .migration import Migration
from .schema_version import SchemaVersionStore
from .versions import MIGRATIONS


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class MigrationRunner:
    def __init__(self, store: PersistenceStore, migrations: list[Migration] | None = None) -> None:
        self.store = store
        self.migrations = sorted(migrations or MIGRATIONS, key=lambda item: item.version)
        self.version_store = SchemaVersionStore(store)

    def pending(self) -> list[Migration]:
        applied = self.version_store.applied_versions()
        return [migration for migration in self.migrations if migration.version not in applied]

    def apply(self, *, dry_run: bool = False) -> dict[str, object]:
        applied_now: list[int] = []
        for migration in self.pending():
            if dry_run:
                if migration.validate:
                    continue
                continue
            try:
                with UnitOfWork(self.store):
                    migration.apply(self.store)
                    if migration.validate:
                        migration.validate(self.store)
                    self.version_store.mark_applied(migration.version, migration.name, utc_now())
                applied_now.append(migration.version)
            except Exception as exc:
                raise RuntimeError(f"migration {migration.version} failed closed: {exc}") from exc
        return {
            "status": "ok",
            "current_version": self.version_store.current_version(),
            "applied": applied_now,
            "dry_run": dry_run,
        }

    def validate(self) -> dict[str, object]:
        for migration in self.migrations:
            if migration.validate and migration.version in self.version_store.applied_versions():
                migration.validate(self.store)
        return {"status": "ok", "current_version": self.version_store.current_version()}
