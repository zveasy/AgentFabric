"""In-memory persistence backend with the same interface as durable stores."""

from __future__ import annotations

from copy import deepcopy


class MemoryPersistenceStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict[str, object]]] = {}

    def initialize(self) -> None:
        self._data.setdefault("_meta", {})

    def put(self, collection: str, key: str, value: dict[str, object]) -> None:
        self._data.setdefault(collection, {})[key] = deepcopy(value)

    def get(self, collection: str, key: str) -> dict[str, object] | None:
        value = self._data.get(collection, {}).get(key)
        return deepcopy(value) if value is not None else None

    def delete(self, collection: str, key: str) -> bool:
        if key in self._data.get(collection, {}):
            del self._data[collection][key]
            return True
        return False

    def list(self, collection: str) -> list[dict[str, object]]:
        return [deepcopy(value) for _, value in sorted(self._data.get(collection, {}).items())]

    def list_tenant(self, collection: str, tenant_id: str) -> list[dict[str, object]]:
        return [
            deepcopy(value)
            for _, value in sorted(self._data.get(collection, {}).items())
            if value.get("tenant_id") == tenant_id
        ]

    def keys(self, collection: str) -> list[str]:
        return sorted(self._data.get(collection, {}))

    def health(self) -> dict[str, object]:
        return {"status": "ok", "backend": "memory", "collections": sorted(self._data)}
