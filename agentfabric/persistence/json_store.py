"""JSON-file persistence backend."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import NamedTemporaryFile


class JsonPersistenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"_meta": {}})

    def put(self, collection: str, key: str, value: dict[str, object]) -> None:
        data = self._read()
        data.setdefault(collection, {})[key] = deepcopy(value)
        self._write(data)

    def get(self, collection: str, key: str) -> dict[str, object] | None:
        value = self._read().get(collection, {}).get(key)
        return deepcopy(value) if value is not None else None

    def delete(self, collection: str, key: str) -> bool:
        data = self._read()
        if key not in data.get(collection, {}):
            return False
        del data[collection][key]
        self._write(data)
        return True

    def list(self, collection: str) -> list[dict[str, object]]:
        return [deepcopy(value) for _, value in sorted(self._read().get(collection, {}).items())]

    def list_tenant(self, collection: str, tenant_id: str) -> list[dict[str, object]]:
        return [
            deepcopy(value)
            for _, value in sorted(self._read().get(collection, {}).items())
            if value.get("tenant_id") == tenant_id
        ]

    def keys(self, collection: str) -> list[str]:
        return sorted(self._read().get(collection, {}))

    def health(self) -> dict[str, object]:
        try:
            data = self._read()
            return {"status": "ok", "backend": "json", "collections": sorted(data)}
        except Exception as exc:
            return {"status": "error", "backend": "json", "error": str(exc)}

    def _read(self) -> dict[str, dict[str, dict[str, object]]]:
        self.initialize()
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False) as handle:
            json.dump(data, handle, sort_keys=True)
            tmp = Path(handle.name)
        tmp.replace(self.path)
