"""Audit bundle redaction helpers."""

from __future__ import annotations


SENSITIVE_KEYS = {"secret", "raw", "password", "token_value", "private_key"}


def redact(value: object) -> object:
    if isinstance(value, dict):
        output: dict[str, object] = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                output[str(key)] = "[REDACTED]"
            else:
                output[str(key)] = redact(item)
        return output
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def contains_raw_sensitive(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS and item != "[REDACTED]":
                return True
            if contains_raw_sensitive(item):
                return True
    if isinstance(value, list):
        return any(contains_raw_sensitive(item) for item in value)
    return False
