"""Application service boundary."""

from __future__ import annotations

from .models import ContractorProfile


class RepositoryService:
    def create(self, record: ContractorProfile) -> ContractorProfile:
        return record
