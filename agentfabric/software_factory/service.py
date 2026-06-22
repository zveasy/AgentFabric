"""Tenant-scoped AI software foundry service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json

from agentfabric.blueprints import BlueprintCatalog
from agentfabric.domain_knowledge import DomainKnowledgeCatalog
from agentfabric.domain_platforms import DomainPlatformCatalog, DomainPlatformDefinition
from agentfabric.enterprise import TenantContext
from agentfabric.errors import AuthorizationError, NotFoundError
from agentfabric.evaluation import RepositoryQualityGate
from agentfabric.events import EventStore
from agentfabric.persistence import PersistenceStore
from agentfabric.repository_factory import RepositoryFactory
from agentfabric.repository_graph import RepositoryGraph
from agentfabric.repository_lifecycle import RepositoryLifecycleService, RepositoryRecord

from .pipeline import RepositoryPackage, SoftwareFactoryPipeline


@dataclass(frozen=True)
class FactoryIdea:
    tenant_id: str
    organization_id: str
    created_by: str
    title: str
    domain: str
    purpose: str
    repository_type: str
    idea_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    @classmethod
    def create(cls, ctx: TenantContext, payload: dict[str, object]) -> "FactoryIdea":
        canonical = json.dumps(
            {
                "tenant_id": ctx.tenant_id,
                "title": payload["title"],
                "domain": payload["domain"],
                "purpose": payload["purpose"],
                "repository_type": payload.get("repository_type", "service"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return cls(
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
            created_by=ctx.principal_id,
            title=str(payload["title"]),
            domain=str(payload["domain"]),
            purpose=str(payload["purpose"]),
            repository_type=str(payload.get("repository_type", "service")),
            idea_id=f"idea-{sha256(canonical.encode()).hexdigest()[:16]}",
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "idea_id": self.idea_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "created_by": self.created_by,
            "title": self.title,
            "domain": self.domain,
            "purpose": self.purpose,
            "repository_type": self.repository_type,
            "created_at": self.created_at.isoformat(),
        }


class SoftwareFoundryService:
    def __init__(self, persistence: PersistenceStore, event_store: EventStore) -> None:
        self.persistence = persistence
        self.event_store = event_store
        self.repositories = RepositoryFactory()
        self.lifecycle = RepositoryLifecycleService(persistence, event_store)
        self.pipeline = SoftwareFactoryPipeline(persistence, event_store)
        self.blueprints = BlueprintCatalog()
        self.knowledge = DomainKnowledgeCatalog()
        self.platforms = DomainPlatformCatalog()
        self.quality_gate = RepositoryQualityGate()

    def create_idea(self, ctx: TenantContext, payload: dict[str, object]) -> FactoryIdea:
        idea = FactoryIdea.create(ctx, payload)
        self.persistence.put("factory_ideas", idea.idea_id, idea.as_dict())
        self.event_store.append("factory.idea.created", idea.idea_id, idea.as_dict())
        return idea

    def generate_repository(
        self,
        ctx: TenantContext,
        payload: dict[str, object],
    ) -> tuple[RepositoryRecord, RepositoryPackage]:
        idea = self._idea(ctx, str(payload["idea_id"]))
        category = str(payload.get("blueprint_category", idea.domain))
        try:
            industry = self.blueprints.get(category)
        except KeyError as exc:
            raise NotFoundError(str(exc)) from exc
        knowledge = self.knowledge.get(_knowledge_domain(idea.domain))
        manifest_payload: dict[str, object] = {
            "name": payload.get("name", idea.title),
            "domain": idea.domain,
            "purpose": idea.purpose,
            "repository_type": payload.get("repository_type", idea.repository_type),
            "dependencies": payload.get("dependencies", ()),
            "apis": payload.get("apis", industry.api_routes),
            "rbac_scopes": payload.get("rbac_scopes", industry.rbac_scopes),
            "events": payload.get("events", industry.event_schemas),
            "observability": payload.get("observability", industry.observability),
            "tests": payload.get("tests", ("unit", "integration", "security")),
            "documentation_requirements": payload.get(
                "documentation_requirements",
                ("README", "architecture", "API", "runbook"),
            ),
            "metadata": {
                "blueprint_id": industry.blueprint_id,
                "knowledge_pack_id": knowledge.pack_id,
            },
        }
        if payload.get("architecture"):
            manifest_payload["architecture"] = payload["architecture"]
        blueprint = self.repositories.create_blueprint(manifest_payload)
        try:
            quality = self.quality_gate.score(
                blueprint.manifest.repository_id,
                ctx.tenant_id,
                {key: float(value) for key, value in dict(payload.get("quality_metrics", {})).items()},
            )
            self.quality_gate.enforce(quality)
        except (AuthorizationError, ValueError) as exc:
            self.event_store.append(
                "factory.quality.failed",
                blueprint.manifest.repository_id,
                {
                    "tenant_id": ctx.tenant_id,
                    "repository_id": blueprint.manifest.repository_id,
                    "reason": str(exc),
                },
            )
            raise
        self.persistence.put("factory_quality_scores", blueprint.manifest.repository_id, quality.as_dict())
        self.event_store.append("factory.quality.passed", blueprint.manifest.repository_id, quality.as_dict())
        record = self.lifecycle.create(ctx, blueprint)
        package = self.pipeline.generate(
            tenant_id=ctx.tenant_id,
            idea=idea.as_dict(),
            blueprint=blueprint,
            signer=ctx.principal_id,
        )
        return record, package

    def register_platform(
        self,
        ctx: TenantContext,
        platform: DomainPlatformDefinition,
    ) -> DomainPlatformDefinition:
        registered = self.platforms.register(platform)
        record = {"tenant_id": ctx.tenant_id, "created_by": ctx.principal_id, **registered.as_dict()}
        self.persistence.put("factory_platforms", f"{ctx.tenant_id}:{registered.name}", record)
        self.event_store.append("factory.platform.registered", registered.platform_id, record)
        return registered

    def list_platforms(self, ctx: TenantContext) -> list[dict[str, object]]:
        custom = self.persistence.list_tenant("factory_platforms", ctx.tenant_id)
        custom_names = {str(item["name"]) for item in custom}
        defaults = [
            {"tenant_id": ctx.tenant_id, "catalog": True, **item.as_dict()}
            for item in self.platforms.list()
            if item.name not in custom_names
        ]
        return sorted([*custom, *defaults], key=lambda item: str(item["name"]))

    def graph(self, ctx: TenantContext) -> RepositoryGraph:
        return RepositoryGraph(self.lifecycle.list(ctx))

    def quality(self, ctx: TenantContext) -> list[dict[str, object]]:
        return self.persistence.list_tenant("factory_quality_scores", ctx.tenant_id)

    def _idea(self, ctx: TenantContext, idea_id: str) -> FactoryIdea:
        value = self.persistence.get("factory_ideas", idea_id)
        if value is None:
            raise NotFoundError("factory idea not found")
        if value.get("tenant_id") != ctx.tenant_id:
            raise AuthorizationError("cross-tenant factory idea access denied")
        return FactoryIdea(
            tenant_id=str(value["tenant_id"]),
            organization_id=str(value["organization_id"]),
            created_by=str(value["created_by"]),
            title=str(value["title"]),
            domain=str(value["domain"]),
            purpose=str(value["purpose"]),
            repository_type=str(value["repository_type"]),
            idea_id=str(value["idea_id"]),
            created_at=datetime.fromisoformat(str(value["created_at"])),
        )


def _knowledge_domain(domain: str) -> str:
    aliases = {
        "construction": "construction",
        "fintech": "treasury",
        "treasury": "treasury",
        "trust": "trust",
        "energy": "energy",
        "manufacturing": "manufacturing",
        "defense": "aerospace",
        "robotics": "manufacturing",
        "aerospace": "aerospace",
    }
    try:
        return aliases[domain]
    except KeyError as exc:
        raise NotFoundError(f"no domain knowledge pack for {domain}") from exc
