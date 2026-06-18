"""Package review model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True)
class PackageReview:
    tenant_id: str
    package_id: str
    rating: int
    review: str = ""
    abuse_report: bool = False
    review_id: str = field(default_factory=lambda: f"rev-{uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def as_dict(self) -> dict[str, object]:
        return {
            "review_id": self.review_id,
            "tenant_id": self.tenant_id,
            "package_id": self.package_id,
            "rating": self.rating,
            "review": self.review,
            "abuse_report": self.abuse_report,
            "created_at": self.created_at.isoformat(),
        }
