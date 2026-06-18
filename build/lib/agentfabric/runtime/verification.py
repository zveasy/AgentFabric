"""
Package integrity: signed agent packages and verification at install/load.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def compute_package_digest(manifest: dict[str, Any], package_root: Path) -> str:
    """
    Compute a deterministic digest of the package (manifest + list of file paths).
    Does not include file contents; used for optional integrity checks.
    """
    h = hashlib.sha256()
    h.update(json.dumps(manifest, sort_keys=True).encode("utf-8"))
    for p in sorted(package_root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(package_root)).encode("utf-8"))
    return h.hexdigest()


def verify_signature(package_root: Path, manifest: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Verify package signature if present. Returns (valid, error_message).
    If no signature is present, returns (True, None) so unsigned packages
    can be allowed in dev; in production, policy can require signature.
    """
    sig_path = package_root / ".agentfabric" / "signature.json"
    if not sig_path.exists():
        return True, None  # No signature: allow (policy may require signature elsewhere)
    try:
        data = json.loads(sig_path.read_text(encoding="utf-8"))
        expected_digest = data.get("digest")
        if not expected_digest:
            return False, "signature.json missing digest"
        actual = compute_package_digest(manifest, package_root)
        if actual != expected_digest:
            return False, "package digest mismatch"
        # Optional: verify cryptographic signature (e.g. sigstore/cosign) here
        return True, None
    except Exception as e:
        return False, str(e)
