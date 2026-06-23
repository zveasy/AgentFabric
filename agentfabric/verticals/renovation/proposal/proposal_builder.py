"""Canonical proposal rendering."""

from agentfabric.verticals.renovation.models import Proposal


class ProposalBuilder:
    def render(self, proposal: Proposal) -> str:
        scope = "\n".join(proposal.scope_of_work)
        payments = "\n".join(
            f"- {item.label}: {item.percentage:g}% (${item.amount:,.2f})"
            for item in proposal.payment_schedule
        )
        timeline = "\n".join(
            f"- Phase {item.sequence}: {item.phase} ({item.duration_days} days)"
            for item in proposal.timeline
        )
        terms = "\n".join(f"- {item}" for item in proposal.terms_and_conditions)
        return (
            f"{proposal.project.title}\n"
            f"Proposal for {proposal.customer.name}\n"
            f"Property: {proposal.project.property_address}\n\n"
            f"Scope of Work\n{scope}\n\n"
            f"Material Estimate: ${proposal.estimate.material_total:,.2f}\n"
            f"Labor Estimate: ${proposal.estimate.labor_total:,.2f}\n"
            f"Project Total: ${proposal.estimate.total:,.2f}\n\n"
            f"Payment Schedule\n{payments}\n\n"
            f"Timeline\n{timeline}\n\n"
            f"Warranty\n{proposal.warranty}\n\n"
            f"Terms and Conditions\n{terms}\n"
        )
