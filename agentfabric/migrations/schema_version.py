"""Schema version metadata helpers."""

from __future__ import annotations

from dataclasses import dataclass

from agentfabric.persistence import PersistenceStore

COLLECTION = "_schema_versions"


@dataclass(frozen=True)
class SchemaVersion:
    version: int
    name: str
    applied_at: str


class SchemaVersionStore:
    def __init__(self, store: PersistenceStore) -> None:
        self.store = store
        self.store.initialize()

    def applied_versions(self) -> set[int]:
        return {int(item["version"]) for item in self.store.list(COLLECTION)}

    def current_version(self) -> int:
        versions = self.applied_versions()
        return max(versions) if versions else 0

    def mark_applied(self, version: int, name: str, applied_at: str) -> None:
        self.store.put(
            COLLECTION,
            str(version),
            {"version": version, "name": name, "applied_at": applied_at},
        )
