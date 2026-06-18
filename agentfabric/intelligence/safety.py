"""Shared safety checks for connector intelligence."""

from __future__ import annotations


SENSITIVE_KEYS = {"raw", "secret", "password", "token_value", "private_key", "credential"}


def require_sanitized_input(payload: dict[str, object]) -> None:
    if _contains_sensitive_key(payload):
        raise ValueError("intelligence services require sanitized connector data")
    if not any(key in payload for key in {"sanitized_payload", "veil_token_ref", "veil_token_refs", "connector_result_id"}):
        raise ValueError("intelligence services require sanitized connector results or VEIL token references")


def _contains_sensitive_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                return True
            if _contains_sensitive_key(item):
                return True
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False
