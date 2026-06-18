"""Connector request and response sandbox limits."""

from __future__ import annotations

from dataclasses import dataclass
import json
from urllib.parse import urlparse


SENSITIVE_KEYS = {"secret", "password", "token", "token_value", "private_key", "credential"}


@dataclass(frozen=True)
class ConnectorSandbox:
    timeout_seconds: int = 30
    max_payload_bytes: int = 64 * 1024
    max_response_bytes: int = 1024 * 1024
    blocked_domains: tuple[str, ...] = ("localhost", "127.0.0.1", "169.254.169.254")

    def validate_request(
        self,
        payload: dict[str, object],
        *,
        allowed_domains: tuple[str, ...],
        allowed_methods: tuple[str, ...],
    ) -> None:
        if len(json.dumps(payload, sort_keys=True).encode("utf-8")) > self.max_payload_bytes:
            raise ValueError("connector payload exceeds sandbox limit")
        if _contains_sensitive(payload):
            raise ValueError("connector payload may not contain credential material")
        method = str(payload.get("method", "GET")).upper()
        if method not in allowed_methods:
            raise ValueError("HTTP method is not allowed")
        url = str(payload.get("url", ""))
        if url:
            domain = (urlparse(url).hostname or "").lower()
            if domain in self.blocked_domains:
                raise ValueError("connector target domain is blocked")
            if allowed_domains and domain not in allowed_domains:
                raise ValueError("connector target domain is not allowlisted")
        timeout = int(payload.get("timeout_seconds", self.timeout_seconds))
        if timeout <= 0 or timeout > self.timeout_seconds:
            raise ValueError("connector timeout exceeds sandbox limit")

    def validate_response(self, response: dict[str, object]) -> None:
        if len(json.dumps(response, sort_keys=True).encode("utf-8")) > self.max_response_bytes:
            raise ValueError("connector response exceeds sandbox limit")
        if _contains_sensitive(response):
            raise ValueError("connector response contains credential material")


def _contains_sensitive(value: object) -> bool:
    if isinstance(value, dict):
        return any(str(key).lower() in SENSITIVE_KEYS or _contains_sensitive(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_sensitive(item) for item in value)
    return False
