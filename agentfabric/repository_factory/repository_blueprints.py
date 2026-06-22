"""Repository blueprint model."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .repository_metadata import RepositoryManifest


@dataclass(frozen=True)
class RepositoryBlueprint:
    blueprint_id: str
    manifest: RepositoryManifest
    files: dict[str, str]

    def as_dict(self) -> dict[str, object]:
        return {
            "blueprint_id": self.blueprint_id,
            "manifest": self.manifest.as_dict(),
            "files": dict(sorted(self.files.items())),
        }

    @property
    def digest(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode()).hexdigest()
