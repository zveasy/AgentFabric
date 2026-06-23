"""Tenant-isolated RenovationOS Foundation service."""

from __future__ import annotations

from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError, NotFoundError
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore

from .estimate import EstimateService
from .events import ESTIMATE_CREATED, ESTIMATE_UPDATED, PROPOSAL_EXPORTED, PROPOSAL_GENERATED
from .marketplace import RENOVATION_FOUNDATION_PACKAGE
from .models import (
    Customer,
    Estimate,
    LaborLine,
    MaterialLine,
    PaymentSchedule,
    Project,
    Proposal,
    ScopeItem,
    Timeline,
)
from .proposal import ProposalService


class RenovationFoundationService:
    def __init__(self, persistence: PersistenceStore, event_store: EventStore) -> None:
        self.persistence = persistence
        self.event_store = event_store
        self.estimates = EstimateService()
        self.proposals = ProposalService()
        self.persistence.put(
            "renovation_marketplace_packages",
            str(RENOVATION_FOUNDATION_PACKAGE["package_id"]),
            {"tenant_id": "system", **RENOVATION_FOUNDATION_PACKAGE},
        )

    def create_estimate(self, ctx: TenantContext, payload: dict[str, object]) -> Estimate:
        ctx.require()
        estimate = self.estimates.create(ctx.tenant_id, payload)
        existing = self.persistence.get("renovation_estimates", estimate.estimate_id)
        record = {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": ctx.principal_id,
            "input": payload,
            "artifact": estimate.as_dict(),
        }
        self.persistence.put("renovation_estimates", estimate.estimate_id, record)
        self.event_store.append(
            ESTIMATE_UPDATED if existing else ESTIMATE_CREATED,
            estimate.estimate_id,
            {
                "tenant_id": ctx.tenant_id,
                "organization_id": ctx.organization_id,
                "estimate_id": estimate.estimate_id,
                "artifact_hash": _artifact_hash(estimate.export_json()),
            },
        )
        return estimate

    def get_estimate(self, ctx: TenantContext, estimate_id: str) -> Estimate:
        value = self._tenant_record(ctx, "renovation_estimates", estimate_id, "estimate")
        return _estimate_from_dict(dict(value["artifact"]))

    def replay_estimate(self, ctx: TenantContext, estimate_id: str) -> Estimate:
        value = self._tenant_record(ctx, "renovation_estimates", estimate_id, "estimate")
        replayed = self.estimates.create(ctx.tenant_id, dict(value["input"]))
        original = _estimate_from_dict(dict(value["artifact"]))
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation estimate replay diverged")
        return replayed

    def create_proposal(self, ctx: TenantContext, payload: dict[str, object]) -> Proposal:
        estimate = self.get_estimate(ctx, str(payload["estimate_id"]))
        proposal = self.proposals.create(ctx.tenant_id, estimate, payload)
        record = {
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": ctx.principal_id,
            "input": payload,
            "artifact": proposal.as_dict(),
        }
        self.persistence.put("renovation_proposals", proposal.proposal_id, record)
        self.event_store.append(
            PROPOSAL_GENERATED,
            proposal.proposal_id,
            {
                "tenant_id": ctx.tenant_id,
                "organization_id": ctx.organization_id,
                "proposal_id": proposal.proposal_id,
                "estimate_id": estimate.estimate_id,
                "template_id": proposal.template_id,
                "template_version": proposal.template_version,
                "artifact_hash": _artifact_hash(proposal.export_json()),
            },
        )
        return proposal

    def get_proposal(self, ctx: TenantContext, proposal_id: str) -> Proposal:
        value = self._tenant_record(ctx, "renovation_proposals", proposal_id, "proposal")
        return _proposal_from_dict(dict(value["artifact"]))

    def replay_proposal(self, ctx: TenantContext, proposal_id: str) -> Proposal:
        value = self._tenant_record(ctx, "renovation_proposals", proposal_id, "proposal")
        payload = dict(value["input"])
        estimate = self.get_estimate(ctx, str(payload["estimate_id"]))
        replayed = self.proposals.create(ctx.tenant_id, estimate, payload)
        original = _proposal_from_dict(dict(value["artifact"]))
        if replayed.export_json() != original.export_json():
            raise ValueError("renovation proposal replay diverged")
        return replayed

    def export_proposal(
        self,
        ctx: TenantContext,
        proposal_id: str,
        export_format: str = "json",
    ) -> dict[str, object]:
        proposal = self.get_proposal(ctx, proposal_id)
        if export_format == "json":
            content = proposal.export_json()
        elif export_format == "text":
            content = proposal.rendered_text
        else:
            raise ValueError("proposal export format must be json or text")
        export = {
            "tenant_id": ctx.tenant_id,
            "proposal_id": proposal_id,
            "format": export_format,
            "content": content,
            "artifact_hash": _artifact_hash(content),
            "template_id": proposal.template_id,
        }
        key = f"{proposal_id}:{export_format}"
        self.persistence.put("renovation_proposal_exports", key, export)
        self.event_store.append(
            PROPOSAL_EXPORTED,
            proposal_id,
            {
                "tenant_id": ctx.tenant_id,
                "proposal_id": proposal_id,
                "format": export_format,
                "artifact_hash": export["artifact_hash"],
            },
        )
        return export

    def marketplace_package(self) -> dict[str, object]:
        return dict(RENOVATION_FOUNDATION_PACKAGE)

    def _tenant_record(
        self,
        ctx: TenantContext,
        collection: str,
        key: str,
        label: str,
    ) -> dict[str, object]:
        ctx.require()
        value = self.persistence.get(collection, key)
        if value is None:
            raise NotFoundError(f"renovation {label} not found")
        if value.get("tenant_id") != ctx.tenant_id:
            raise AuthorizationError(f"cross-tenant renovation {label} access denied")
        return value


def _artifact_hash(value: str) -> str:
    from hashlib import sha256

    return sha256(value.encode()).hexdigest()


def _estimate_from_dict(value: dict[str, object]) -> Estimate:
    return Estimate(
        estimate_id=str(value["estimate_id"]),
        tenant_id=str(value["tenant_id"]),
        project_id=str(value["project_id"]),
        scope_description=str(value["scope_description"]),
        scope_items=tuple(ScopeItem(**item) for item in value["scope_items"]),
        material_lines=tuple(MaterialLine(**item) for item in value["material_lines"]),
        labor_lines=tuple(LaborLine(**item) for item in value["labor_lines"]),
        material_total=float(value["material_total"]),
        labor_total=float(value["labor_total"]),
        subtotal=float(value["subtotal"]),
        contingency_percentage=float(value["contingency_percentage"]),
        contingency=float(value["contingency"]),
        taxable_amount=float(value["taxable_amount"]),
        tax_percentage=float(value["tax_percentage"]),
        tax=float(value["tax"]),
        total=float(value["total"]),
        notes=str(value["notes"]),
        rate_table_version=str(value.get("rate_table_version", "renovation-rates-v1")),
    )


def _proposal_from_dict(value: dict[str, object]) -> Proposal:
    return Proposal(
        proposal_id=str(value["proposal_id"]),
        tenant_id=str(value["tenant_id"]),
        customer=Customer(**dict(value["customer"])),
        project=Project(**dict(value["project"])),
        estimate=_estimate_from_dict(dict(value["estimate"])),
        template_id=str(value["template_id"]),
        template_version=str(value["template_version"]),
        style=str(value["style"]),
        scope_of_work=tuple(str(item) for item in value["scope_of_work"]),
        payment_schedule=tuple(PaymentSchedule(**item) for item in value["payment_schedule"]),
        timeline=tuple(Timeline(**item) for item in value["timeline"]),
        warranty=str(value["warranty"]),
        terms_and_conditions=tuple(str(item) for item in value["terms_and_conditions"]),
        rendered_text=str(value["rendered_text"]),
    )
