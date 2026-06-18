"""Replaceable persistence interfaces for durable AgentFabric state."""

from __future__ import annotations

from typing import Protocol


class PersistenceStore(Protocol):
    def initialize(self) -> None:
        """Prepare storage structures."""

    def put(self, collection: str, key: str, value: dict[str, object]) -> None:
        """Persist one JSON-serializable document."""

    def get(self, collection: str, key: str) -> dict[str, object] | None:
        """Load one document by collection/key."""

    def delete(self, collection: str, key: str) -> bool:
        """Delete one document. Returns True if it existed."""

    def list(self, collection: str) -> list[dict[str, object]]:
        """List documents in a collection."""

    def list_tenant(self, collection: str, tenant_id: str) -> list[dict[str, object]]:
        """List tenant-scoped documents."""

    def keys(self, collection: str) -> list[str]:
        """List document keys in a collection."""

    def health(self) -> dict[str, object]:
        """Return operational storage health."""
