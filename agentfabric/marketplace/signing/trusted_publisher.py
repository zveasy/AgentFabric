"""Trusted publisher registry."""

from __future__ import annotations


class TrustedPublisherRegistry:
    def __init__(self) -> None:
        self._fingerprints: dict[str, str] = {}

    def trust(self, publisher_id: str, fingerprint: str) -> None:
        self._fingerprints[publisher_id] = fingerprint

    def fingerprint_for(self, publisher_id: str) -> str | None:
        return self._fingerprints.get(publisher_id)
