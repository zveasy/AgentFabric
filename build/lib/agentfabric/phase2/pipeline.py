"""Publish pipeline: validate, verify signature, index."""

from __future__ import annotations

from hashlib import sha256

from agentfabric.errors import ValidationError
from agentfabric.phase2.models import PackageUpload, compute_payload_digest


class SignatureVerifier:
    """Deterministic signing helper for package integrity checks."""

    def __init__(self) -> None:
        self._developer_signing_secrets: dict[str, str] = {}

    def register_developer_secret(self, developer_id: str, secret: str) -> None:
        self._developer_signing_secrets[developer_id] = secret

    def verify_upload(self, developer_id: str, upload: PackageUpload) -> str:
        secret = self._developer_signing_secrets.get(developer_id)
        if secret is None:
            raise ValidationError("developer has no registered signing secret")

        digest = compute_payload_digest(upload.payload)
        material = f"{developer_id}:{digest}:{secret}".encode("utf-8")
        expected_signature = sha256(material).hexdigest()
        if upload.signature != expected_signature:
            raise ValidationError("signature verification failed")
        return digest


class ManifestValidator:
    """Versioned manifest validator for hosted uploads."""

    REQUIRED_FIELDS = {
        "manifest_version",
        "name",
        "description",
        "entrypoint",
        "permissions",
    }

    def validate(self, manifest: dict[str, object]) -> None:
        missing = sorted(self.REQUIRED_FIELDS.difference(manifest.keys()))
        if missing:
            raise ValidationError(f"manifest missing fields: {', '.join(missing)}")
        if manifest["manifest_version"] != "v1":
            raise ValidationError("only manifest_version=v1 is supported")
