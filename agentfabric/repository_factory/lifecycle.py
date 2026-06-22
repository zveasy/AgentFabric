"""Repository factory facade."""

from __future__ import annotations

from .manifest_builder import ManifestBuilder
from .repository_blueprints import RepositoryBlueprint
from .scaffolding import RepositoryScaffolder


class RepositoryFactory:
    def __init__(self) -> None:
        self.manifests = ManifestBuilder()
        self.scaffolder = RepositoryScaffolder()

    def create_blueprint(self, payload: dict[str, object]) -> RepositoryBlueprint:
        return self.scaffolder.scaffold(self.manifests.build(payload))
