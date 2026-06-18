"""
AgentFabric production scaffolding and runtime compatibility exports.
"""

__version__ = "0.2.0"

from agentfabric.platform import AgentFabricPlatform
from agentfabric.production.control_plane import ProductionControlPlane
from agentfabric.runtime.manifest import Manifest, load_manifest


def create_app(*args, **kwargs):
    """Import the server lazily so domain packages do not depend on FastAPI startup."""
    from agentfabric.server import create_app as server_create_app

    return server_create_app(*args, **kwargs)

__all__ = [
    "__version__",
    "AgentFabricPlatform",
    "ProductionControlPlane",
    "create_app",
    "load_manifest",
    "Manifest",
]
