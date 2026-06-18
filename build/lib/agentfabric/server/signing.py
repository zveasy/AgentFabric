"""Real package signature verification adapters."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from hashlib import sha256

from agentfabric.errors import ValidationError


@dataclass(frozen=True)
class VerificationResult:
    payload_digest: str
    verifier: str
    detail: str


class CosignVerifier:
    """Verifies signatures using cosign verify-blob."""

    def __init__(self, cosign_bin: str = "cosign") -> None:
        self.cosign_bin = cosign_bin

    def verify_blob(
        self,
        *,
        payload: bytes,
        signature: str,
        key_path: str | None = None,
        certificate_path: str | None = None,
        cert_identity: str | None = None,
        cert_oidc_issuer: str | None = None,
    ) -> VerificationResult:
        if shutil.which(self.cosign_bin) is None:
            raise ValidationError("cosign binary is not installed")
        with tempfile.NamedTemporaryFile(delete=False) as payload_file, tempfile.NamedTemporaryFile(delete=False) as sig_file:
            payload_file.write(payload)
            sig_file.write(signature.encode("utf-8"))
            payload_file.flush()
            sig_file.flush()
            cmd = [self.cosign_bin, "verify-blob", "--signature", sig_file.name, payload_file.name]
            if key_path:
                cmd.extend(["--key", key_path])
            if certificate_path:
                cmd.extend(["--certificate", certificate_path])
            if cert_identity:
                cmd.extend(["--certificate-identity", cert_identity])
            if cert_oidc_issuer:
                cmd.extend(["--certificate-oidc-issuer", cert_oidc_issuer])
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise ValidationError(f"cosign verification failed: {result.stderr.strip()}")
            digest = sha256(payload).hexdigest()
            return VerificationResult(payload_digest=digest, verifier="cosign", detail=result.stdout.strip())


class DigestFallbackVerifier:
    """Fallback verifier for environments lacking cosign."""

    def verify_blob(self, *, payload: bytes, signature: str, **_: object) -> VerificationResult:
        digest = sha256(payload).hexdigest()
        if signature != digest:
            raise ValidationError("fallback signature mismatch")
        return VerificationResult(payload_digest=digest, verifier="digest-fallback", detail="digest matched")
