"""Payment processors with Stripe integration."""

from __future__ import annotations

from dataclasses import dataclass
import json

import stripe

from agentfabric.errors import ValidationError


@dataclass(frozen=True)
class PaymentResult:
    provider: str
    provider_txn_id: str
    amount: float
    currency: str
    status: str


class PaymentProcessor:
    def charge(self, *, tenant_id: str, amount: float, currency: str, idempotency_key: str) -> PaymentResult:
        raise NotImplementedError


class StripePaymentProcessor(PaymentProcessor):
    """Real Stripe payment processor."""

    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    def charge(self, *, tenant_id: str, amount: float, currency: str, idempotency_key: str) -> PaymentResult:
        if not self.api_key:
            raise ValidationError("stripe api key is not configured")
        if amount < 0:
            raise ValidationError("amount cannot be negative")
        stripe.api_key = self.api_key
        intent = stripe.PaymentIntent.create(
            amount=max(1, int(round(amount * 100))),
            currency=currency.lower(),
            metadata={"tenant_id": tenant_id},
            idempotency_key=idempotency_key,
            confirm=False,
            automatic_payment_methods={"enabled": True},
        )
        return PaymentResult(
            provider="stripe",
            provider_txn_id=intent["id"],
            amount=amount,
            currency=currency.upper(),
            status=str(intent.get("status", "pending")),
        )


class MockPaymentProcessor(PaymentProcessor):
    """Deterministic processor for tests/development."""

    def charge(self, *, tenant_id: str, amount: float, currency: str, idempotency_key: str) -> PaymentResult:
        if amount < 0:
            raise ValidationError("amount cannot be negative")
        return PaymentResult(
            provider="mock",
            provider_txn_id=f"mock:{tenant_id}:{idempotency_key}",
            amount=amount,
            currency=currency.upper(),
            status="succeeded",
        )


def parse_stripe_webhook_event(*, payload: bytes, signature: str | None, webhook_secret: str | None) -> dict:
    """Parse/verify Stripe webhook payload.

    If webhook secret is configured, the signature is required and validated.
    In test/local mode without a secret, payload is accepted as plain JSON.
    """
    if webhook_secret:
        if not signature:
            raise ValidationError("missing Stripe-Signature header")
        try:
            return stripe.Webhook.construct_event(payload=payload, sig_header=signature, secret=webhook_secret)
        except Exception as exc:
            raise ValidationError(f"invalid stripe webhook: {exc}") from exc
    try:
        return json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid webhook json: {exc}") from exc
