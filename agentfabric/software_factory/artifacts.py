"""Signed deterministic software factory artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class FactoryArtifact:
    stage: str
    repository_id: str
    content: dict[str, object]
    signer: str
    signature: str

    @classmethod
    def create(
        cls,
        stage: str,
        repository_id: str,
        content: dict[str, object],
        signer: str,
    ) -> "FactoryArtifact":
        signature = sha256(
            json.dumps(
                {"stage": stage, "repository_id": repository_id, "content": content, "signer": signer},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return cls(stage, repository_id, content, signer, signature)

    def as_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "repository_id": self.repository_id,
            "content": self.content,
            "signer": self.signer,
            "signature": self.signature,
        }
