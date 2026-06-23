"""Serializable renovation model helpers."""

from __future__ import annotations

from dataclasses import asdict
import json


class SerializableModel:
    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def export_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
