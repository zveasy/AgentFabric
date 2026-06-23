"""Renovation API route contract metadata."""

ROUTES = {
    "estimate_create": ("POST", "/renovation/estimate", "renovation.estimate.write"),
    "proposal_create": ("POST", "/renovation/proposal", "renovation.proposal.write"),
    "estimate_get": ("GET", "/renovation/estimate/{estimate_id}", "renovation.estimate.read"),
    "proposal_get": ("GET", "/renovation/proposal/{proposal_id}", "renovation.proposal.read"),
    "proposal_export": ("POST", "/renovation/proposal/export", "renovation.proposal.write"),
}
