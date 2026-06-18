"""Signature verification for marketplace packages."""

from __future__ import annotations

from agentfabric.errors import ValidationError

from .package_signature import PackageSignature
from .signing_key import SigningKey
from .trusted_publisher import TrustedPublisherRegistry


class SignatureVerifier:
    def __init__(self, trusted_publishers: TrustedPublisherRegistry, *, allow_unsigned_local: bool = False) -> None:
        self.trusted_publishers = trusted_publishers
        self.allow_unsigned_local = allow_unsigned_local

    def verify(self, *, publisher_id: str, manifest_hash: str, signature: str, key: SigningKey | None = None) -> str:
        if not signature:
            if self.allow_unsigned_local:
                return "unsigned-local"
            raise ValidationError("unsigned packages are not allowed")
        trusted = self.trusted_publishers.fingerprint_for(publisher_id)
        if trusted is None:
            raise ValidationError("publisher is not trusted")
        if key is None:
            raise ValidationError("signing key is required for local verification")
        expected = PackageSignature.sign(manifest_hash, key)
        if expected.fingerprint != trusted or expected.signature != signature:
            raise ValidationError("package signature verification failed")
        return expected.fingerprint
