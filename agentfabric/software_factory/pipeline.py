"""Auditable software generation pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore
from agentfabric.repository_factory import RepositoryBlueprint

from .api_agent import ApiAgent
from .architecture_agent import ArchitectureAgent
from .artifacts import FactoryArtifact
from .backend_agent import BackendAgent
from .database_agent import DatabaseAgent
from .deployment_agent import DeploymentAgent
from .documentation_agent import DocumentationAgent
from .frontend_agent import FrontendAgent
from .release_agent import ReleaseAgent
from .repository_generator import RepositoryGenerator
from .requirements_agent import RequirementsAgent
from .security_agent import SecurityAgent
from .test_agent import TestAgent


STAGES = (
    RequirementsAgent,
    ArchitectureAgent,
    RepositoryGenerator,
    ApiAgent,
    DatabaseAgent,
    BackendAgent,
    FrontendAgent,
    TestAgent,
    DocumentationAgent,
    SecurityAgent,
    DeploymentAgent,
    ReleaseAgent,
)


@dataclass(frozen=True)
class RepositoryPackage:
    repository_id: str
    tenant_id: str
    blueprint: dict[str, object]
    artifacts: tuple[FactoryArtifact, ...]
    status: str = "validated"

    def as_dict(self) -> dict[str, object]:
        return {
            "repository_id": self.repository_id,
            "tenant_id": self.tenant_id,
            "blueprint": self.blueprint,
            "artifacts": [artifact.as_dict() for artifact in self.artifacts],
            "status": self.status,
        }


class SoftwareFactoryPipeline:
    def __init__(self, persistence: PersistenceStore, event_store: EventStore) -> None:
        self.persistence = persistence
        self.event_store = event_store

    def generate(
        self,
        *,
        tenant_id: str,
        idea: dict[str, object],
        blueprint: RepositoryBlueprint,
        signer: str,
    ) -> RepositoryPackage:
        if not tenant_id or not signer:
            raise ValueError("tenant and signer are required")
        context: dict[str, object] = {"idea": idea, "blueprint": blueprint.as_dict()}
        artifacts: list[FactoryArtifact] = []
        for stage_type in STAGES:
            artifact = stage_type().run(blueprint.manifest.repository_id, context, signer=signer)
            artifacts.append(artifact)
            record = {"tenant_id": tenant_id, **artifact.as_dict()}
            key = f"{blueprint.manifest.repository_id}:{artifact.stage}"
            self.persistence.put("factory_artifacts", key, record)
            self.event_store.append("factory.artifact.generated", blueprint.manifest.repository_id, record)
            context[artifact.stage] = artifact.as_dict()
        package = RepositoryPackage(
            repository_id=blueprint.manifest.repository_id,
            tenant_id=tenant_id,
            blueprint=blueprint.as_dict(),
            artifacts=tuple(artifacts),
        )
        self.persistence.put("factory_repository_packages", package.repository_id, package.as_dict())
        self.event_store.append("factory.repository.packaged", package.repository_id, package.as_dict())
        return package
