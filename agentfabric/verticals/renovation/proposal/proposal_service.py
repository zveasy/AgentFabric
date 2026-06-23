"""Deterministic proposal construction."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json

from agentfabric.verticals.renovation.models import Customer, Estimate, Project, Proposal
from agentfabric.verticals.renovation.templates import load_template

from .payment_terms import PaymentTerms
from .proposal_builder import ProposalBuilder
from .scope_formatter import ScopeFormatter
from .timeline_generator import TimelineGenerator
from .warranty_templates import WarrantyTemplates


class ProposalService:
    def __init__(self) -> None:
        self.scope = ScopeFormatter()
        self.payments = PaymentTerms()
        self.timelines = TimelineGenerator()
        self.warranties = WarrantyTemplates()
        self.builder = ProposalBuilder()

    def create(
        self,
        tenant_id: str,
        estimate: Estimate,
        payload: dict[str, object],
    ) -> Proposal:
        if estimate.tenant_id != tenant_id:
            raise PermissionError("cross-tenant estimate access denied")
        template = load_template(str(payload.get("template_id", "standard_proposal")))
        customer = Customer(**dict(payload["customer"]))
        project = Project(**dict(payload["project"]))
        scope = self.scope.format(estimate)
        payment_schedule = self.payments.build(estimate.total, list(template["payment_terms"]))
        timeline = self.timelines.build(list(template["project_phases"]))
        warranty = self.warranties.render(int(template["warranty_months"]))
        identity = {
            "tenant_id": tenant_id,
            "estimate_id": estimate.estimate_id,
            "customer": customer.as_dict(),
            "project": project.as_dict(),
            "template_id": template["template_id"],
            "template_version": template["version"],
        }
        proposal_id = f"proposal-{_digest(identity)[:20]}"
        proposal = Proposal(
            proposal_id=proposal_id,
            tenant_id=tenant_id,
            customer=customer,
            project=project,
            estimate=estimate,
            template_id=str(template["template_id"]),
            template_version=str(template["version"]),
            style=str(template["style"]),
            scope_of_work=scope,
            payment_schedule=payment_schedule,
            timeline=timeline,
            warranty=warranty,
            terms_and_conditions=tuple(str(item) for item in template["clauses"]),
            rendered_text="",
        )
        return replace(proposal, rendered_text=self.builder.render(proposal))


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
