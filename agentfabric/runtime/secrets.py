"""
Secrets: no secrets in manifests or agent code. The runtime injects secrets
via environment (e.g. AGENTFABRIC_SECRET_<key>) or a secrets API that only
the runtime can call. This module provides resolution from env for local use.
"""

from __future__ import annotations

import os
from typing import Any


def get_secret(key: str, default: Any = None) -> Any:
    """
    Resolve a secret by key. In local runtime, reads from environment
    AGENTFABRIC_SECRET_<KEY> (uppercase). In production, this can be
    replaced with a vault or managed secrets API.
    """
    env_key = f"AGENTFABRIC_SECRET_{key.upper()}"
    return os.environ.get(env_key, default)


def inject_secrets_into_env(secrets: dict[str, str]) -> dict[str, str]:
    """Build env vars for sandbox: AGENTFABRIC_SECRET_* from secrets dict."""
    out = {}
    for k, v in secrets.items():
        out[f"AGENTFABRIC_SECRET_{k.upper()}"] = v
    return out
