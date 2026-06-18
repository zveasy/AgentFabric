"""Unit-of-work wrapper for atomic persistence updates."""

from __future__ import annotations

from copy import deepcopy
from types import TracebackType

from .memory_store import MemoryPersistenceStore
from .sqlite_store import SQLitePersistenceStore


class UnitOfWork:
    def __init__(self, store: object) -> None:
        self.store = store
        self._snapshot: dict[str, dict[str, dict[str, object]]] | None = None
        self._sqlite_context = None

    def __enter__(self) -> "UnitOfWork":
        if isinstance(self.store, MemoryPersistenceStore):
            self._snapshot = deepcopy(self.store._data)
        if isinstance(self.store, SQLitePersistenceStore):
            self._sqlite_context = self.store.transaction()
            self._sqlite_context.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if isinstance(self.store, MemoryPersistenceStore) and exc_type is not None and self._snapshot is not None:
            self.store._data = self._snapshot
        if self._sqlite_context is not None:
            self._sqlite_context.__exit__(exc_type, exc, tb)
        return False

    def put(self, collection: str, key: str, value: dict[str, object]) -> None:
        self.store.put(collection, key, value)

    def delete(self, collection: str, key: str) -> bool:
        return bool(self.store.delete(collection, key))
