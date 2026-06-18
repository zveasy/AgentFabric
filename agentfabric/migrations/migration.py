"""Migration model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agentfabric.persistence import PersistenceStore

MigrationFn = Callable[[PersistenceStore], None]


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: MigrationFn
    validate: MigrationFn | None = None
