"""Top-level façade that composes phases 1-4 services."""

from agentfabric.phase1.runtime import AgentOrchestrator
from agentfabric.phase2.auth import ApiKeyAuthService
from agentfabric.phase2.billing import BillingService
from agentfabric.phase2.registry import RegistryService
from agentfabric.phase2.reviews import ReviewService
from agentfabric.phase3.collaboration import CollaborationOrchestrator, CollaborationPolicy
from agentfabric.phase3.workflow import WorkflowEngine
from agentfabric.phase4.audit import ImmutableAuditLog
from agentfabric.phase4.marketplace import PrivateMarketplaceService
from agentfabric.phase4.rbac import RbacService
from agentfabric.phase4.sla import SlaCatalog


class AgentFabricPlatform:
    """Composed services for production phases 1-4."""

    def __init__(self) -> None:
        self.runtime = AgentOrchestrator()
        self.auth = ApiKeyAuthService()
        self.registry = RegistryService()
        self.reviews = ReviewService()
        self.billing = BillingService()
        self.workflow = WorkflowEngine()
        self.collaboration = CollaborationOrchestrator(CollaborationPolicy())
        self.rbac = RbacService()
        self.audit = ImmutableAuditLog()
        self.private_marketplaces = PrivateMarketplaceService()
        self.sla_catalog = SlaCatalog()
