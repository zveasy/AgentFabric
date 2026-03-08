"""Sandbox policy and guarded boundary operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from agentfabric.errors import AuthorizationError


@dataclass(frozen=True)
class SandboxPolicy:
    allow_network: bool = False
    allowed_filesystem_paths: tuple[str, ...] = ()


class Sandbox:
    """Restricted interface for filesystem/network operations."""

    def __init__(self, policy: SandboxPolicy) -> None:
        self._policy = policy

    @property
    def policy(self) -> SandboxPolicy:
        return self._policy

    def read_file(self, path: str) -> str:
        target = Path(path).resolve()
        allowed = [Path(p).resolve() for p in self._policy.allowed_filesystem_paths]
        if not any(str(target).startswith(str(prefix)) for prefix in allowed):
            raise AuthorizationError(f"sandbox denied filesystem read: {path}")
        return target.read_text(encoding="utf-8")

    def request_url(self, url: str) -> dict[str, str]:
        if not self._policy.allow_network:
            raise AuthorizationError("sandbox denied network access")
        parsed = urlparse(url)
        return {"scheme": parsed.scheme, "netloc": parsed.netloc, "path": parsed.path}
