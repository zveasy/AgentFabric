"""Application service boundary."""

from __future__ import annotations

from .models import ProjectIntake


class RepositoryService:
    def create(self, record: ProjectIntake) -> ProjectIntake:
        return record
