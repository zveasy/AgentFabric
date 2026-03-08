"""AgentFabric production scaffolding.

This package implements phases 1-4 service primitives.
"""

from agentfabric.platform import AgentFabricPlatform
from agentfabric.production.control_plane import ProductionControlPlane
from agentfabric.server import create_app

__all__ = ["AgentFabricPlatform", "ProductionControlPlane", "create_app"]
