from __future__ import annotations

import unittest
from hashlib import sha256

from agentfabric.errors import AuthorizationError, ValidationError
from agentfabric.phase2.billing import BillingService
from agentfabric.phase2.models import MeterEvent, PackageUpload, Rating
from agentfabric.phase2.registry import RegistryService
from agentfabric.phase2.reviews import ReviewService


def make_signature(developer_id: str, payload: bytes, secret: str) -> str:
    digest = sha256(payload).hexdigest()
    return sha256(f"{developer_id}:{digest}:{secret}".encode("utf-8")).hexdigest()


def make_upload(signature: str, payload: bytes = b"print('hello')") -> PackageUpload:
    return PackageUpload(
        package_id="research-agent",
        version="1.0.0",
        namespace="dev-a",
        category="research",
        permissions=("tool.web.search", "tool.memory.read"),
        manifest={
            "manifest_version": "v1",
            "name": "Research Agent",
            "description": "Finds sources",
            "entrypoint": "agent.py:run",
            "permissions": ["tool.web.search", "tool.memory.read"],
        },
        payload=payload,
        signature=signature,
    )


class Phase2MarketplaceTests(unittest.TestCase):
    def test_publish_and_discovery_with_permissions_filter(self) -> None:
        registry = RegistryService()
        registry.register_developer_signing_secret("dev-a", "secret-a")
        payload = b"artifact"
        upload = make_upload(make_signature("dev-a", payload, "secret-a"), payload=payload)
        package = registry.publish("dev-a", upload)
        result = registry.list_packages(required_permissions={"tool.web.search"})
        self.assertEqual(package.fqid, "dev-a/research-agent:1.0.0")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["package_id"], "research-agent")

    def test_publish_denies_wrong_namespace_and_bad_signature(self) -> None:
        registry = RegistryService()
        registry.register_developer_signing_secret("dev-a", "secret-a")
        upload = make_upload(signature="bad-signature")
        with self.assertRaises(ValidationError):
            registry.publish("dev-a", upload)

        payload = b"x"
        valid = make_upload(make_signature("dev-a", payload, "secret-a"), payload=payload)
        renamed = PackageUpload(
            package_id=valid.package_id,
            version=valid.version,
            namespace="another-dev",
            category=valid.category,
            permissions=valid.permissions,
            manifest=valid.manifest,
            payload=valid.payload,
            signature=valid.signature,
        )
        with self.assertRaises(AuthorizationError):
            registry.publish("dev-a", renamed)

    def test_reviews_and_billing_idempotency(self) -> None:
        reviews = ReviewService()
        reviews.submit_rating(
            Rating(
                tenant_id="tenant-1",
                package_fqid="dev-a/research-agent:1.0.0",
                user_id="u1",
                stars=5,
                review="Very useful agent.",
            )
        )
        summary = reviews.get_rating_summary("dev-a/research-agent:1.0.0")
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["avg_stars"], 5.0)
        with self.assertRaises(ValidationError):
            reviews.submit_rating(
                Rating(
                    tenant_id="tenant-1",
                    package_fqid="dev-a/research-agent:1.0.0",
                    user_id="u2",
                    stars=1,
                    review="This is malware",
                )
            )

        billing = BillingService()
        event = MeterEvent(
            event_type="run",
            tenant_id="tenant-1",
            actor_id="u1",
            package_fqid="dev-a/research-agent:1.0.0",
            idempotency_key="evt-1",
        )
        billing.enqueue(event)
        billing.enqueue(event)
        billing.process_queue()
        invoice = billing.build_invoice("tenant-1")
        self.assertEqual(invoice["total"], 0.01)
        self.assertEqual(invoice["lines"][0]["quantity"], 1)


if __name__ == "__main__":
    unittest.main()
