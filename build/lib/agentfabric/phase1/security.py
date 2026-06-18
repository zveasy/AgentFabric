"""Security components: permissions, secrets, integrity."""

from __future__ import annotations

from hashlib import sha256

from agentfabric.errors import AuthorizationError, ValidationError
from agentfabric.phase1.manifest import AgentManifest


class PermissionEnforcer:
    """Deny-by-default permission checks against manifest grants."""

    def check(self, manifest: AgentManifest, permission: str) -> None:
        if permission not in manifest.permissions:
            raise AuthorizationError(f"permission denied: {permission}")


class RuntimeSecrets:
    """Runtime-only secret store; never persisted into manifests/code."""

    def __init__(self) -> None:
        self._secrets: dict[str, str] = {}

    def put(self, key: str, value: str) -> None:
        self._secrets[key] = value

    def get(self, key: str) -> str:
        if key not in self._secrets:
            raise ValidationError(f"unknown secret: {key}")
        return self._secrets[key]


class PackageIntegrityVerifier:
    """Simple signer registration and package signature verification."""

    def __init__(self) -> None:
        self._signer_keys: dict[str, str] = {}

    def register_signer_key(self, signer_id: str, key: str) -> None:
        self._signer_keys[signer_id] = key

    def verify(self, signer_id: str, payload: bytes, signature: str) -> str:
        key = self._signer_keys.get(signer_id)
        if key is None:
            raise ValidationError("unknown signer")
        digest = sha256(payload).hexdigest()
        expected = sha256(f"{signer_id}:{digest}:{key}".encode("utf-8")).hexdigest()
        if expected != signature:
            raise ValidationError("package integrity verification failed")
        return digest

    def sign(self, signer_id: str, payload: bytes) -> str:
        key = self._signer_keys.get(signer_id)
        if key is None:
            raise ValidationError("unknown signer")
        digest = sha256(payload).hexdigest()
        return sha256(f"{signer_id}:{digest}:{key}".encode("utf-8")).hexdigest()
