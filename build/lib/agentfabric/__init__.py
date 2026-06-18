"""
AgentFabric production scaffolding and runtime compatibility exports.
"""

__version__ = "0.2.0"

from agentfabric.platform import AgentFabricPlatform
from agentfabric.production.control_plane import ProductionControlPlane
from agentfabric.runtime.manifest import Manifest, load_manifest
from agentfabric.server import create_app

__all__ = [
    "__version__",
    "AgentFabricPlatform",
    "ProductionControlPlane",
    "create_app",
    "load_manifest",
    "Manifest",
]
