<<<<<<< HEAD
"""AgentFabric production scaffolding.

This package implements phases 1-4 service primitives.
"""

from agentfabric.platform import AgentFabricPlatform
from agentfabric.production.control_plane import ProductionControlPlane
from agentfabric.server import create_app

__all__ = ["AgentFabricPlatform", "ProductionControlPlane", "create_app"]
=======
"""
AgentFabric: Universal marketplace and runtime for AI agents.
"""

__version__ = "0.1.0"

from agentfabric.runtime.manifest import load_manifest, Manifest

__all__ = ["__version__", "load_manifest", "Manifest"]
>>>>>>> origin/main
