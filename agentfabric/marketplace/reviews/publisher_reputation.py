"""Publisher reputation service."""

from __future__ import annotations

from agentfabric.persistence import PersistenceStore


class PublisherReputationService:
    def __init__(self, persistence: PersistenceStore) -> None:
        self.persistence = persistence

    def reputation(self, publisher_id: str) -> dict[str, object]:
        packages = [item for item in self.persistence.list("marketplace_packages") if item["publisher_tenant_id"] == publisher_id]
        installs = [
            item for item in self.persistence.list("marketplace_installs")
            if item.get("publisher_tenant_id") == publisher_id
        ]
        reviews = [
            review for review in self.persistence.list("marketplace_reviews")
            if any(package["package_id"] == review["package_id"] for package in packages)
        ]
        avg = sum(int(item["rating"]) for item in reviews) / len(reviews) if reviews else 0.0
        abuse = sum(1 for item in reviews if item.get("abuse_report"))
        return {
            "publisher_id": publisher_id,
            "package_count": len(packages),
            "install_count": len(installs),
            "average_rating": avg,
            "abuse_reports": abuse,
            "reputation_score": max(0.0, round((avg / 5 if avg else 0.8) - (abuse * 0.1), 4)),
        }
