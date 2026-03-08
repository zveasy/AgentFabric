"""Security hardening pipeline for packages and runtime policies."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from agentfabric.errors import ValidationError
from agentfabric.phase1.security import PackageIntegrityVerifier


@dataclass(frozen=True)
class SignaturePolicy:
    require_trusted_signer: bool = True
    trusted_signers: tuple[str, ...] = ()


class SbomGenerator:
    """Generates a minimal SBOM-style descriptor for uploaded artifacts."""

    def generate(self, *, package_name: str, version: str, payload: bytes) -> dict[str, Any]:
        return {
            "component": package_name,
            "version": version,
            "artifact_sha256": sha256(payload).hexdigest(),
            "size_bytes": len(payload),
            "format": "spdx-lite",
        }


class MalwareScanner:
    """Heuristic scanner hook for uploaded package payloads."""

    DANGEROUS_MARKERS = (
        "rm -rf /",
        "curl http://",
        "wget http://",
        "subprocess.Popen(",
        "socket.connect(",
    )

    def scan(self, payload: bytes) -> dict[str, Any]:
        text = payload.decode("utf-8", errors="ignore").lower()
        findings = [marker for marker in self.DANGEROUS_MARKERS if marker.lower() in text]
        return {"clean": not findings, "findings": findings}


class PackageSecurityPipeline:
    """Combines signature policy, integrity verification, SBOM, and malware checks."""

    def __init__(
        self,
        *,
        integrity_verifier: PackageIntegrityVerifier | None = None,
        sbom_generator: SbomGenerator | None = None,
        malware_scanner: MalwareScanner | None = None,
        signature_policy: SignaturePolicy | None = None,
    ) -> None:
        self.integrity_verifier = integrity_verifier or PackageIntegrityVerifier()
        self.sbom_generator = sbom_generator or SbomGenerator()
        self.malware_scanner = malware_scanner or MalwareScanner()
        self.signature_policy = signature_policy or SignaturePolicy()

    def validate(
        self,
        *,
        signer_id: str,
        package_name: str,
        version: str,
        payload: bytes,
        signature: str,
    ) -> dict[str, Any]:
        if self.signature_policy.require_trusted_signer and self.signature_policy.trusted_signers:
            if signer_id not in self.signature_policy.trusted_signers:
                raise ValidationError("signer is not trusted by signature policy")

        payload_digest = self.integrity_verifier.verify(signer_id, payload, signature)
        sbom = self.sbom_generator.generate(package_name=package_name, version=version, payload=payload)
        malware_report = self.malware_scanner.scan(payload)
        if not malware_report["clean"]:
            raise ValidationError(f"malware scanner rejected package: {json.dumps(malware_report['findings'])}")
        return {
            "payload_digest": payload_digest,
            "sbom": sbom,
            "malware_report": malware_report,
        }
