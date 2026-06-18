"""Payment processors with Stripe integration."""

from __future__ import annotations

from dataclasses import dataclass
import json

from agentfabric.quotas import QuotaPolicy

try:
    import stripe
except ImportError:  # pragma: no cover - exercised only when optional dependency is absent
    stripe = None

from agentfabric.errors import ValidationError


@dataclass(frozen=True)
class BillingPlan:
    plan_id: str
    quota_policy: QuotaPolicy
    features: tuple[str, ...]
    retention_days: int
    support_level: str
    marketplace_permissions: tuple[str, ...]
    max_users: int
    max_agents: int
    max_workflows: int

    def as_dict(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "quota_limits": self.quota_policy.as_dict(),
            "features": list(self.features),
            "retention_days": self.retention_days,
            "support_level": self.support_level,
            "marketplace_permissions": list(self.marketplace_permissions),
            "max_users": self.max_users,
            "max_agents": self.max_agents,
            "max_workflows": self.max_workflows,
        }


BILLING_PLANS = {
    "dev": BillingPlan(
        plan_id="dev",
        quota_policy=QuotaPolicy(agents_per_tenant=3, workflow_runs_per_day=25, memory_records=100, marketplace_installs=10),
        features=("runtime", "mesh", "memory"),
        retention_days=14,
        support_level="community",
        marketplace_permissions=("install",),
        max_users=3,
        max_agents=3,
        max_workflows=25,
    ),
    "team": BillingPlan(
        plan_id="team",
        quota_policy=QuotaPolicy(agents_per_tenant=25, workflow_runs_per_day=1000, memory_records=10000, marketplace_installs=250),
        features=("runtime", "mesh", "memory", "recovery", "marketplace"),
        retention_days=90,
        support_level="standard",
        marketplace_permissions=("install", "publish"),
        max_users=50,
        max_agents=25,
        max_workflows=1000,
    ),
    "enterprise": BillingPlan(
        plan_id="enterprise",
        quota_policy=QuotaPolicy(
            agents_per_tenant=1000,
            workflow_runs_per_day=100000,
            concurrent_workflows=500,
            memory_records=1000000,
            marketplace_installs=10000,
        ),
        features=("runtime", "mesh", "memory", "recovery", "marketplace", "audit_export", "sso"),
        retention_days=365,
        support_level="premium",
        marketplace_permissions=("install", "publish", "private"),
        max_users=10000,
        max_agents=1000,
        max_workflows=100000,
    ),
    "internal": BillingPlan(
        plan_id="internal",
        quota_policy=QuotaPolicy(
            agents_per_tenant=100000,
            workflow_runs_per_day=1000000,
            concurrent_workflows=10000,
            memory_records=10000000,
            marketplace_installs=100000,
        ),
        features=("all",),
        retention_days=3650,
        support_level="internal",
        marketplace_permissions=("install", "publish", "private", "admin"),
        max_users=100000,
        max_agents=100000,
        max_workflows=1000000,
    ),
}


def get_billing_plan(plan_id: str) -> BillingPlan:
    if plan_id not in BILLING_PLANS:
        raise ValidationError(f"unknown billing plan: {plan_id}")
    return BILLING_PLANS[plan_id]


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
        if stripe is None:
            raise ValidationError("stripe package is not installed")
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
