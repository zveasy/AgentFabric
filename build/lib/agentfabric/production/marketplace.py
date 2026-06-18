"""Marketplace production modules: moderation and settlement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agentfabric.errors import ValidationError
from agentfabric.phase2.models import Rating
from agentfabric.production.store import ProductionStore


class ModerationService:
    """Queues reviews for moderation and applies admin decisions."""

    BANNED_TERMS = {"malware", "phishing", "scam", "steal"}

    def __init__(self, store: ProductionStore) -> None:
        self._store = store

    def submit_review(self, rating: Rating) -> int:
        lowered = rating.review.lower()
        requires_review = any(term in lowered for term in self.BANNED_TERMS)
        status = "pending" if requires_review else "approved"
        review_id = self._store.submit_review(rating, status=status)
        if requires_review:
            self._store.enqueue_review_moderation(review_id, reason="abuse-pattern")
        return review_id

    def pending(self) -> list[dict]:
        return self._store.pending_reviews()

    def moderate(self, review_id: int, approved: bool) -> None:
        self._store.moderate_review(review_id, approved=approved)


class PaymentGateway(Protocol):
    def charge(self, *, tenant_id: str, amount: float, currency: str, idempotency_key: str) -> str: ...


@dataclass
class MockPaymentGateway:
    """Mock gateway used in tests/local runs."""

    provider: str = "mock"

    def charge(self, *, tenant_id: str, amount: float, currency: str, idempotency_key: str) -> str:
        if amount < 0:
            raise ValidationError("amount cannot be negative")
        return f"{self.provider}:{tenant_id}:{currency}:{idempotency_key}"


class StripePaymentGateway:
    """Optional Stripe adapter hook (networked call intentionally omitted)."""

    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    def charge(self, *, tenant_id: str, amount: float, currency: str, idempotency_key: str) -> str:
        if not self.api_key:
            raise ValidationError("stripe api key not configured")
        # The actual API call is intentionally delegated to deployment-specific integrations.
        return f"stripe:{tenant_id}:{currency}:{idempotency_key}"


class SettlementService:
    """Writes settlement events to billing ledger and charges gateway."""

    def __init__(self, store: ProductionStore, gateway: PaymentGateway | None = None) -> None:
        self._store = store
        self._gateway = gateway or MockPaymentGateway()

    def settle_invoice(self, *, tenant_id: str, total: float, currency: str, idempotency_key: str) -> str:
        tx_id = self._gateway.charge(
            tenant_id=tenant_id,
            amount=total,
            currency=currency,
            idempotency_key=idempotency_key,
        )
        self._store.add_billing_ledger_line(
            tenant_id=tenant_id,
            event_type="settlement",
            quantity=1,
            unit_price=total,
        )
        return tx_id
