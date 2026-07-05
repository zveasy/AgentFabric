"""Allowlist-based deterministic customer portal projections."""

from __future__ import annotations

from hashlib import sha256
import json

from .models import CustomerPortalView, CustomerVisibilityPolicy


DEFAULT_VISIBILITY_POLICY = CustomerVisibilityPolicy(
    policy_id="renovation-customer-visibility-v1",
    version="1.0.0",
    allowed_sections=(
        "project",
        "scope",
        "timeline",
        "progress",
        "photos",
        "change_orders",
        "invoices",
        "communications",
    ),
    require_photo_approval=True,
    exclude_internal_notes=True,
    exclude_internal_financials=True,
)

FORBIDDEN_KEYS = {
    "financial_hash",
    "history_hash",
    "schedule_hash",
    "artifact_hash",
    "margin",
    "profitability",
    "vendor",
    "payable",
    "cost_overrun",
    "risk",
    "rbac",
    "created_by",
    "organization_id",
}


class CustomerPortalService:
    def view(
        self,
        tenant_id: str,
        customer_id: str,
        generated_date: str,
        projects: tuple[dict[str, object], ...],
        communications: tuple[dict[str, object], ...],
        policy: CustomerVisibilityPolicy = DEFAULT_VISIBILITY_POLICY,
    ) -> CustomerPortalView:
        value = {
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "generated_date": generated_date,
            "policy_id": policy.policy_id,
            "projects": list(projects),
            "communications": list(communications),
        }
        self.validate(value)
        view_id = f"portal-{_digest(value)[:20]}"
        return CustomerPortalView(
            portal_view_id=view_id,
            projects=projects,
            communications=communications,
            view_hash=_digest({**value, "portal_view_id": view_id}),
            **{key: item for key, item in value.items() if key not in {
                "projects", "communications"
            }},
        )

    def validate(self, value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = str(key).lower()
                if any(forbidden in normalized for forbidden in FORBIDDEN_KEYS):
                    raise ValueError(f"customer portal contains forbidden field: {key}")
                self.validate(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                self.validate(item)


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
