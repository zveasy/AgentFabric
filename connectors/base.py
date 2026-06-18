from __future__ import annotations

from typing import Protocol


class Connector(Protocol):
    name: str

    def healthcheck(self) -> bool:
        """Return True when the connector is available."""
