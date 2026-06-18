"""Package signature helper."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .signing_key import SigningKey


@dataclass(frozen=True)
class PackageSignature:
    signature: str
    fingerprint: str

    @classmethod
    def sign(cls, manifest_hash: str, key: SigningKey) -> "PackageSignature":
        return cls(
            signature=sha256(f"{manifest_hash}:{key.secret}".encode("utf-8")).hexdigest(),
            fingerprint=key.fingerprint,
        )
