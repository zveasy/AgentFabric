"""Ratings and moderation primitives."""

from __future__ import annotations

from collections import defaultdict

from agentfabric.errors import ValidationError
from agentfabric.phase2.models import Rating


class ReviewService:
    """Stores package ratings with basic abuse moderation."""

    BANNED_TERMS = {"malware", "phishing", "scam"}

    def __init__(self) -> None:
        self._ratings: defaultdict[str, list[Rating]] = defaultdict(list)

    def submit_rating(self, rating: Rating) -> None:
        if rating.stars < 1 or rating.stars > 5:
            raise ValidationError("stars must be between 1 and 5")
        lowered = rating.review.lower()
        if any(term in lowered for term in self.BANNED_TERMS):
            raise ValidationError("review rejected by moderation policy")
        self._ratings[rating.package_fqid].append(rating)

    def get_rating_summary(self, package_fqid: str) -> dict[str, float | int]:
        entries = self._ratings.get(package_fqid, [])
        if not entries:
            return {"count": 0, "avg_stars": 0.0}
        total = sum(item.stars for item in entries)
        return {"count": len(entries), "avg_stars": round(total / len(entries), 2)}
