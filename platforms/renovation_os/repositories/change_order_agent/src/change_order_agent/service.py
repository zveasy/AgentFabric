"""Application service boundary."""

from __future__ import annotations

from .models import ChangeOrder


class RepositoryService:
    def create(self, record: ChangeOrder) -> ChangeOrder:
        return record
