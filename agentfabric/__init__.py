"""
AgentFabric: Universal marketplace and runtime for AI agents.
"""

__version__ = "0.1.0"

from agentfabric.runtime.manifest import load_manifest, Manifest

__all__ = ["__version__", "load_manifest", "Manifest"]
