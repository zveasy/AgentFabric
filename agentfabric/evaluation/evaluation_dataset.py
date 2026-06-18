"""Tenant-scoped evaluation datasets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from .evaluation_case import EvaluationCase


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class EvaluationDataset:
    tenant_id: str
    organization_id: str
    name: str
    cases: tuple[EvaluationCase, ...]
    created_by: str
    dataset_id: str = field(default_factory=lambda: f"eval-dataset-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=utc_now)

    def validate(self) -> None:
        if not self.tenant_id or not self.organization_id:
            raise ValueError("tenant context is required")
        if not self.name:
            raise ValueError("dataset name is required")
        if not self.cases:
            raise ValueError("dataset requires at least one case")
        for case in self.cases:
            case.validate()

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "name": self.name,
            "cases": [case.as_dict() for case in self.cases],
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "EvaluationDataset":
        return cls(
            dataset_id=str(value["dataset_id"]),
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            name=str(value["name"]),
            cases=tuple(EvaluationCase.from_dict(item) for item in value.get("cases", ())),
            created_by=str(value.get("created_by", "")),
            created_at=datetime.fromisoformat(str(value["created_at"])) if value.get("created_at") else utc_now(),
        )
