"""Entitlement verification."""

from __future__ import annotations

from datetime import datetime, timezone

from agentfabric.errors import AuthorizationError

from .entitlement import Entitlement


class LicenseChecker:
    def verify(self, entitlement: Entitlement | None) -> None:
        if entitlement is None or not entitlement.active:
            raise AuthorizationError("package entitlement is required")
        if entitlement.expires_at and entitlement.expires_at <= datetime.now(tz=timezone.utc):
            raise AuthorizationError("package entitlement has expired")
