"""Customer-facing portal projection models."""

from dataclasses import dataclass

from agentfabric.verticals.renovation.models.base import SerializableModel


@dataclass(frozen=True)
class CustomerVisibilityPolicy(SerializableModel):
    policy_id: str
    version: str
    allowed_sections: tuple[str, ...]
    require_photo_approval: bool
    exclude_internal_notes: bool
    exclude_internal_financials: bool


@dataclass(frozen=True)
class CustomerPortalView(SerializableModel):
    portal_view_id: str
    tenant_id: str
    customer_id: str
    generated_date: str
    policy_id: str
    projects: tuple[dict[str, object], ...]
    communications: tuple[dict[str, object], ...]
    view_hash: str
