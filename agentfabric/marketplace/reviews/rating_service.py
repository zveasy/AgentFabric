"""Package rating service."""

from __future__ import annotations

from agentfabric.persistence import PersistenceStore

from .review import PackageReview


class RatingService:
    def __init__(self, persistence: PersistenceStore) -> None:
        self.persistence = persistence

    def submit(self, review: PackageReview) -> PackageReview:
        self.persistence.put("marketplace_reviews", review.review_id, review.as_dict())
        return review

    def summary(self, package_id: str) -> dict[str, object]:
        reviews = [item for item in self.persistence.list("marketplace_reviews") if item["package_id"] == package_id]
        count = len(reviews)
        average = sum(int(item["rating"]) for item in reviews) / count if count else 0.0
        return {"package_id": package_id, "count": count, "average_rating": average}
