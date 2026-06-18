"""Publisher signing key metadata."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class SigningKey:
    publisher_id: str
    secret: str

    @property
    def fingerprint(self) -> str:
        return sha256(f"{self.publisher_id}:{self.secret}".encode("utf-8")).hexdigest()
