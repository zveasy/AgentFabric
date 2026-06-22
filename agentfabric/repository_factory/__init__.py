"""Deterministic repository factory."""

from .dependency_graph import RepositoryDependencyGraph
from .lifecycle import RepositoryFactory
from .manifest_builder import ManifestBuilder
from .package_structure import build_package_structure
from .project_templates import PROJECT_TEMPLATES, project_template
from .repository_blueprints import RepositoryBlueprint
from .repository_metadata import REPOSITORY_TYPES, RepositoryManifest
from .scaffolding import RepositoryScaffolder

__all__ = [
    "PROJECT_TEMPLATES",
    "REPOSITORY_TYPES",
    "ManifestBuilder",
    "RepositoryBlueprint",
    "RepositoryDependencyGraph",
    "RepositoryFactory",
    "RepositoryManifest",
    "RepositoryScaffolder",
    "build_package_structure",
    "project_template",
]
