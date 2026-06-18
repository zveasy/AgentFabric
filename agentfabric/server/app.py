"""FastAPI application with auth middleware and OpenAPI docs."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
import shutil
import time
from collections import defaultdict
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from agent_connectors import (
    ConnectorExecutionPolicy as EnterpriseConnectorPolicy,
    ConnectorManifest as EnterpriseConnectorManifest,
    EnterpriseConnectorService,
)
from agent_observability import AgentMetric, OperationalIntelligenceService
from agentfabric.audit_bundle import AuditBundleExporter
from agentfabric.cloud import CloudRuntime, RuntimeConfig, RuntimeJob, Worker
from agentfabric.cloud.queue_backends import MemoryJobQueue, RedisJobQueue, SQLiteJobQueue
from agentfabric.cloud.scheduler import ScheduledJob, SchedulerService
from agentfabric.config import validate_production_safety
from agentfabric.collaboration import CollaborationCoordinator, ContextStore, MeshWorkflowEngine, TaskNode
from agentfabric.connectors import ConnectorCredentials, ConnectorManifest, ConnectorPolicy, ConnectorRegistry
from agentfabric.economics import CostTracker, MarginAnalyzer, PackageRevenue, PricingPolicy, RevenueTracker, TenantProfitability
from agentfabric.enterprise import Membership, MembershipService, Team, TenantContext, TenantIsolation, TenantService
from agentfabric.errors import AgentFabricError, AuthorizationError, ConflictError, NotFoundError, ValidationError
from agentfabric.evaluation import EvaluationCase, EvaluationDataset, EvaluationRunner, QualityGateService
from agentfabric.feedback import FeedbackService
from agentfabric.events import EventStore, EventType
from agentfabric.federation import (
    FederatedOrg,
    FederationService,
    RemoteAgent,
    RemoteCapability,
    RemoteDelegation,
    TrustAgreement,
)
from agentfabric.federation.messaging import FederatedMessage
from agentfabric.governance import (
    AgentOrganization,
    AgentTeam,
    Charter,
    ConsensusPolicy,
    GovernancePolicy,
    GovernanceService,
    HumanApprovalQueue,
    Proposal,
    ProposalStatus,
    Vote,
)
from agentfabric.identity import AgentCertificate, AgentIdentity, AgentPassport
from agentfabric.marketplace import (
    InstallService,
    MarketplaceRegistryService,
    PackageDependency,
    PackageManifest,
    PackageMetadata,
    PackageSignature,
    PublishService,
    SignatureVerifier,
    SigningKey,
    TrustedPublisherRegistry,
)
from agentfabric.marketplace.reviews import PackageReview, PublisherReputationService, RatingService
from agentfabric.marketplace.scanning import MarketplaceScanner
from agentfabric.memory import DurableMemoryStore
from agentfabric.metering import MeteringService
from agentfabric.mesh import AgentDirectory, AgentDiscovery, MeshMessage, MessageBus, MessageType
from agentfabric.migrations import MigrationRunner
from agentfabric.observability import DeploymentHealth, MetricsRegistry, TenantUsageMetrics
from agentfabric.phase2.models import Rating
from agentfabric.persistence import MemoryPersistenceStore
from agentfabric.production.control_plane import ProductionControlPlane
from agentfabric.quotas import LimitEnforcer, QuotaPolicy, QuotaTracker
from agentfabric.reputation import ReputationService
from agentfabric.recovery import ReplayRecoveryEngine
from agentfabric.server.auth import AuthService, require_scopes
from agentfabric.server.config import Settings, get_settings
from agentfabric.server.database import build_session_factory, run_migrations
from agentfabric.server.errors import domain_exception_response, http_exception_response
from agentfabric.server.models import Principal
from agentfabric.server.payments import MockPaymentProcessor, StripePaymentProcessor, get_billing_plan, parse_stripe_webhook_event
from agentfabric.server.queue import InMemoryQueueBackend, RedisQueueBackend
from agentfabric.server.schemas import (
    BillingEventRequest,
    HealthResponse,
    InstallPackageRequest,
    InvoiceResponse,
    IssueTokenRequest,
    ListPackagesResponse,
    PackageResponse,
    PublishPackageRequest,
    QueueEnqueueRequest,
    QueueMessageResponse,
    RegisterPrincipalRequest,
    RotateTokenRequest,
    TokenResponse,
)
from agentfabric.server.services import AuditService, BillingService, PackageService, QueueService
from agentfabric.server.signing import CosignVerifier, DigestFallbackVerifier
from agentfabric.tools import ToolManifest, ToolPermission, ToolRegistry, ToolRouter
from veil_client import MockVeilClient

HTTP_REQUEST_COUNT = Counter(
    "agentfabric_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)
HTTP_REQUEST_LATENCY = Histogram(
    "agentfabric_http_request_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
)


def choose_queue_backend(settings: Settings):
    if settings.redis_url.startswith("redis://"):
        try:
            return RedisQueueBackend(settings.redis_url)
        except Exception:
            return InMemoryQueueBackend()
    return InMemoryQueueBackend()


def choose_signing_verifier(settings: Settings):
    if shutil.which("cosign") is not None:
        return CosignVerifier()
    if settings.strict_signing:
        raise RuntimeError("strict signing is enabled but cosign is not available")
    return DigestFallbackVerifier()


def choose_cloud_queue(settings: Settings):
    if settings.cloud_queue_backend == "sqlite":
        return SQLiteJobQueue(settings.cloud_queue_sqlite_path)
    if settings.cloud_queue_backend == "redis":
        return RedisJobQueue(settings.redis_url, fallback=settings.environment != "production")
    return MemoryJobQueue()


def _mesh_passport(
    *,
    agent_id: str,
    name: str,
    version: str,
    owner: str,
    organization: str,
    capabilities: list[str],
    fingerprint: str,
) -> AgentPassport:
    identity = AgentIdentity.create(
        agent_id=agent_id,
        name=name,
        version=version,
        owner=owner,
        organization=organization,
        capabilities=capabilities,
        signing_fingerprint=fingerprint,
    )
    return AgentPassport(
        identity=identity,
        certificate=AgentCertificate.issue(agent_id=agent_id, signing_fingerprint=fingerprint),
    )


def _build_default_directory() -> AgentDirectory:
    directory = AgentDirectory()
    for passport in [
        _mesh_passport(
            agent_id="planner-agent",
            name="PlannerAgent",
            version="1.0.0",
            owner="agentfabric",
            organization="agentfabric",
            capabilities=["planning"],
            fingerprint="planner-fp",
        ),
        _mesh_passport(
            agent_id="research-agent",
            name="ResearchAgent",
            version="1.0.0",
            owner="agentfabric",
            organization="agentfabric",
            capabilities=["research", "retrieval"],
            fingerprint="research-fp",
        ),
        _mesh_passport(
            agent_id="web-agent",
            name="WebAgent",
            version="1.0.0",
            owner="agentfabric",
            organization="agentfabric",
            capabilities=["research", "retrieval"],
            fingerprint="web-fp",
        ),
        _mesh_passport(
            agent_id="document-agent",
            name="DocumentAgent",
            version="1.0.0",
            owner="agentfabric",
            organization="agentfabric",
            capabilities=["research", "analysis", "retrieval"],
            fingerprint="document-fp",
        ),
        _mesh_passport(
            agent_id="code-agent",
            name="CodeAgent",
            version="1.0.0",
            owner="agentfabric",
            organization="agentfabric",
            capabilities=["coding", "execution"],
            fingerprint="code-fp",
        ),
        _mesh_passport(
            agent_id="compliance-agent",
            name="ComplianceAgent",
            version="1.0.0",
            owner="agentfabric",
            organization="agentfabric",
            capabilities=["analysis", "review"],
            fingerprint="compliance-fp",
        ),
        _mesh_passport(
            agent_id="reviewer-agent",
            name="ReviewerAgent",
            version="1.0.0",
            owner="agentfabric",
            organization="agentfabric",
            capabilities=["review"],
            fingerprint="reviewer-fp",
        ),
    ]:
        directory.register(passport)
    return directory


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    validate_production_safety(settings)
    try:
        from agentfabric.observability.logging_config import configure_logging
        configure_logging(level=settings.log_level, json_logs=settings.json_logs)
    except Exception:
        pass
    if settings.auto_migrate:
        run_migrations(settings.database_url)
    session_factory, _ = build_session_factory(settings)
    control_plane = ProductionControlPlane(db_path=settings.production_db_path)
    auth = AuthService(settings)
    queue_backend = choose_queue_backend(settings)
    signing_verifier = choose_signing_verifier(settings)
    payment_processor = StripePaymentProcessor(settings.stripe_api_key) if settings.stripe_api_key else MockPaymentProcessor()
    durable_store = MemoryPersistenceStore()
    migration_result = MigrationRunner(durable_store).apply()
    tenant_service = TenantService(durable_store)
    membership_service = MembershipService(durable_store)
    isolation = TenantIsolation()
    quota_tracker = QuotaTracker()
    limit_enforcer = LimitEnforcer(quota_tracker)
    metering = MeteringService(durable_store)
    cost_tracker = CostTracker(durable_store)
    revenue_tracker = RevenueTracker(durable_store)
    margin_analyzer = MarginAnalyzer(costs=cost_tracker, revenue=revenue_tracker)
    tenant_profitability = TenantProfitability(margin_analyzer)
    package_revenue = PackageRevenue(durable_store)
    pricing_policy = PricingPolicy()
    mesh_directory = _build_default_directory()
    mesh_discovery = AgentDiscovery(mesh_directory)
    veil = MockVeilClient()
    event_store = EventStore(persistence=durable_store)
    operational_intelligence = OperationalIntelligenceService(durable_store, event_store)
    enterprise_connectors = EnterpriseConnectorService(
        persistence=durable_store,
        event_store=event_store,
        veil_client=veil,
        production=settings.environment == "production",
    )
    governance_approvals = HumanApprovalQueue(durable_store)
    governance = GovernanceService(
        persistence=durable_store,
        event_store=event_store,
        veil_client=veil,
        approvals=governance_approvals,
    )
    federation = FederationService(persistence=durable_store, event_store=event_store, veil_client=veil)
    runtime_config = RuntimeConfig(
        queue_backend=settings.cloud_queue_backend,
        sqlite_path=settings.cloud_queue_sqlite_path,
        redis_url=settings.redis_url,
        max_attempts=settings.queue_max_attempts,
        worker_lease_seconds=settings.worker_lease_seconds,
        heartbeat_timeout_seconds=settings.worker_heartbeat_timeout_seconds,
        production_fail_closed=settings.environment == "production",
    )
    cloud_queue = choose_cloud_queue(settings)
    context_store = ContextStore(persistence=durable_store)
    reputation = ReputationService(persistence=durable_store)
    evaluation_runner = EvaluationRunner(
        persistence=durable_store,
        event_store=event_store,
        veil_client=veil,
        reputation=reputation,
    )
    quality_gates = QualityGateService()
    feedback_service = FeedbackService(persistence=durable_store, event_store=event_store, reputation=reputation)
    memory_store = DurableMemoryStore(durable_store)
    marketplace_registry = MarketplaceRegistryService(durable_store)
    trusted_publishers = TrustedPublisherRegistry()
    marketplace_verifier = SignatureVerifier(trusted_publishers, allow_unsigned_local=settings.environment != "production")
    marketplace_publish = PublishService(
        registry=marketplace_registry,
        verifier=marketplace_verifier,
        event_store=event_store,
    )
    marketplace_install = InstallService(
        registry=marketplace_registry,
        persistence=durable_store,
        event_store=event_store,
    )
    marketplace_reviews = RatingService(durable_store)
    publisher_reputation = PublisherReputationService(durable_store)
    message_bus = MessageBus(directory=mesh_directory, veil_client=veil, tenant_id="default")
    workflow_engine = MeshWorkflowEngine(
        context_store=context_store,
        event_store=event_store,
        reputation=reputation,
    )
    coordinator = CollaborationCoordinator(discovery=mesh_discovery, workflow_engine=workflow_engine)

    def _runtime_entitlement_check(job: RuntimeJob) -> None:
        package_id = job.payload.get("package_id")
        if package_id:
            marketplace_install.verify_runtime_entitlement(tenant_id=job.tenant_id, package_id=str(package_id))

    def _runtime_governance_check(job: RuntimeJob) -> None:
        proposal_id = job.payload.get("proposal_id")
        if not proposal_id:
            raise AuthorizationError("governance action jobs require proposal_id")
        proposal = governance.get_proposal(str(proposal_id))
        if proposal.tenant_id != job.tenant_id:
            raise AuthorizationError("cross-tenant governance job denied")
        if proposal.status not in {ProposalStatus.APPROVED.value, ProposalStatus.EXECUTED.value}:
            raise AuthorizationError("governance action is not approved")

    def _runtime_federation_check(job: RuntimeJob) -> None:
        agreement_id = job.payload.get("trust_agreement_id")
        if not agreement_id:
            raise AuthorizationError("federation runtime jobs require trust_agreement_id")
        agreement = federation.registry.get_agreement(str(agreement_id))
        if agreement.tenant_id != job.tenant_id or not agreement.is_active():
            raise AuthorizationError("active federation trust agreement is required")

    def _runtime_spend_check(job: RuntimeJob) -> None:
        category = {
            "agent_run": "agent_run",
            "workflow_step": "workflow_run",
            "tool_execution": "tool_execution",
            "connector_sync": "connector_sync",
            "connector_search": "tool_execution",
            "connector_document_fetch": "tool_execution",
            "marketplace_package": "marketplace_execution",
            "remote_delegation": "federation_delegation",
            "evaluation_run": "evaluation_run",
            "audit_export": "audit_bundle_export",
        }.get(job.job_type, "queue_worker_runtime")
        try:
            cost_tracker.enforce(job.tenant_id, category, source_id=job.job_id)
        except AuthorizationError:
            event_store.append("economics.spend_limit.exceeded", job.job_id, {"tenant_id": job.tenant_id, "job_id": job.job_id, "category": category})
            raise

    cloud_runtime = CloudRuntime(
        queue=cloud_queue,
        persistence=durable_store,
        event_store=event_store,
        veil_client=veil,
        config=runtime_config,
        quota_enforcer=limit_enforcer,
        quota_policy=lambda tenant_id: _tenant_policy(tenant_id),
    )
    cloud_runtime.dispatcher.entitlement_check = _runtime_entitlement_check
    cloud_runtime.dispatcher.governance_check = _runtime_governance_check
    cloud_runtime.dispatcher.federation_check = _runtime_federation_check
    cloud_runtime.dispatcher.spend_check = _runtime_spend_check
    connector_registry = ConnectorRegistry(
        persistence=durable_store,
        event_store=event_store,
        veil_client=veil,
        runtime=cloud_runtime,
    )
    tool_router = ToolRouter(
        connector_registry=connector_registry,
        audit_exporter=AuditBundleExporter(persistence=durable_store, event_store=event_store),
    )
    tool_registry = ToolRegistry(
        persistence=durable_store,
        event_store=event_store,
        veil_client=veil,
        router=tool_router,
        runtime=cloud_runtime,
    )
    scheduler = SchedulerService(persistence=durable_store, event_store=event_store, runtime=cloud_runtime)
    metrics_registry = MetricsRegistry()
    deployment_health = DeploymentHealth(persistence=durable_store, runtime=cloud_runtime)
    if settings.environment == "production":
        readiness = deployment_health.ready(fail_closed=True)
        if readiness["status"] != "ok":
            raise RuntimeError("production readiness checks failed")

    def _tenant_context(request: Request) -> TenantContext:
        principal = require_scopes(request, [])
        tenant = tenant_service.get(principal.tenant_id)
        organization_id = tenant.organization_id if tenant else principal.tenant_id
        return isolation.require_context(
            TenantContext(
                tenant_id=principal.tenant_id,
                organization_id=organization_id,
                principal_id=principal.principal_id,
                roles=principal.scopes,
                is_global_admin="tenant.global" in principal.scopes,
            )
        )

    def _tenant_policy(tenant_id: str) -> QuotaPolicy:
        stored = durable_store.get("quota_policies", tenant_id)
        if stored:
            return QuotaPolicy.from_dict(stored)
        tenant = tenant_service.get(tenant_id)
        plan = get_billing_plan(tenant.billing_plan if tenant else "dev")
        return plan.quota_policy

    def _assert_tenant_access(request: Request, tenant_id: str, scopes: list[str]):
        principal = require_scopes(request, scopes)
        if principal.tenant_id != tenant_id and "tenant.global" not in principal.scopes:
            raise HTTPException(status_code=403, detail="cross-tenant access denied")
        return principal

    def _workflow_owner(workflow_id: str) -> dict[str, object] | None:
        return durable_store.get("workflows", workflow_id)

    def _assert_workflow_tenant(ctx: TenantContext, workflow_id: str) -> None:
        owner = _workflow_owner(workflow_id)
        if owner is None:
            return
        isolation.assert_tenant(ctx, owner)

    def _marketplace_plan_allows(ctx: TenantContext, permission: str) -> None:
        tenant = tenant_service.get(ctx.tenant_id)
        plan = get_billing_plan(tenant.billing_plan if tenant else "dev")
        if permission not in plan.marketplace_permissions and "admin" not in plan.marketplace_permissions:
            raise HTTPException(status_code=403, detail=f"billing plan does not allow marketplace {permission}")

    def _governance_policy(ctx: TenantContext, policy_id: str = "default") -> GovernancePolicy:
        stored = durable_store.get("governance_policies", f"{ctx.tenant_id}:{policy_id}")
        if stored:
            return GovernancePolicy.from_dict(stored)
        return GovernancePolicy(
            policy_id=policy_id,
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
        )

    def _assert_governance_tenant(ctx: TenantContext, item: dict[str, object]) -> None:
        try:
            isolation.assert_tenant(ctx, item)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    def _manifest_from_payload(payload: dict, ctx: TenantContext) -> PackageManifest:
        return PackageManifest(
            package_id=payload["package_id"],
            name=payload.get("name", payload["package_id"]),
            version=payload["version"],
            publisher_tenant_id=ctx.tenant_id,
            agent_identity_id=payload["agent_identity_id"],
            runtime_requirements=payload.get("runtime_requirements", {}),
            tool_permissions=tuple(payload.get("tool_permissions", ())),
            connector_requirements=tuple(payload.get("connector_requirements", ())),
            connector_permissions=tuple(payload.get("connector_permissions", ())),
            dependencies=tuple(PackageDependency.from_dict(item) for item in payload.get("dependencies", ())),
            license_type=payload.get("license_type", "free"),
            pricing_model=payload.get("pricing_model", "free"),
        )

    def _connector_manifest_from_payload(payload: dict) -> ConnectorManifest:
        return ConnectorManifest(
            connector_type=payload["connector_type"],
            display_name=payload.get("display_name", payload["connector_type"]),
            capabilities=tuple(payload.get("capabilities", ("sync", "search", "fetch"))),
            scopes=tuple(payload.get("scopes", ())),
            data_classes=tuple(payload.get("data_classes", ())),
            webhook_supported=bool(payload.get("webhook_supported", False)),
            metadata=dict(payload.get("metadata", {})),
        )

    def _connector_credentials_from_payload(payload: dict) -> ConnectorCredentials:
        credentials = dict(payload.get("credentials", {}))
        return ConnectorCredentials(
            credential_ref=str(credentials.get("credential_ref", "")),
            provider=str(credentials.get("provider", payload.get("connector_type", ""))),
        )

    def _connector_policy_from_payload(payload: dict) -> ConnectorPolicy:
        policy = dict(payload.get("policy", {}))
        return ConnectorPolicy(
            allowed_operations=tuple(policy.get("allowed_operations", ("sync", "search", "fetch", "webhook", "health"))),
            allowed_data_classes=tuple(policy.get("allowed_data_classes", payload.get("data_classes", ()))),
            max_results=int(policy.get("max_results", 100)),
            require_veil=bool(policy.get("require_veil", True)),
        )

    def _tool_manifest_from_payload(payload: dict) -> ToolManifest:
        return ToolManifest(
            name=payload.get("name", payload["tool_type"]),
            tool_type=payload["tool_type"],
            description=payload.get("description", ""),
            version=payload.get("version", "1.0.0"),
            required_connector_type=payload.get("required_connector_type"),
            metadata=dict(payload.get("metadata", {})),
        )

    def _tool_permission_from_payload(payload: dict) -> ToolPermission:
        permission = dict(payload.get("permission", {}))
        return ToolPermission(
            required_rbac_scope=str(permission.get("required_rbac_scope", "tools.execute")),
            required_tenant_context=bool(permission.get("required_tenant_context", True)),
            required_connector_policy=bool(permission.get("required_connector_policy", True)),
            required_veil_policy_check=bool(permission.get("required_veil_policy_check", True)),
            governance_approval_required=bool(permission.get("governance_approval_required", False)),
            result_persistence_allowed=bool(permission.get("result_persistence_allowed", True)),
            allowed_output_classifications=tuple(permission.get("allowed_output_classifications", ("public", "internal"))),
        )

    def _latest_quality(ctx: TenantContext, target_type: str, target_id: str) -> dict[str, object]:
        results = [
            item for item in durable_store.list_tenant("evaluation_results", ctx.tenant_id)
            if item.get("target_type") == target_type and item.get("target_id") == target_id
        ]
        if not results:
            return {"target_type": target_type, "target_id": target_id, "status": "unknown", "overall_score": None}
        latest = sorted(results, key=lambda item: str(item.get("created_at", "")))[-1]
        return {
            "target_type": target_type,
            "target_id": target_id,
            "status": "measured",
            "run_id": latest["run_id"],
            "overall_score": latest["overall_score"],
            "metrics": latest["metrics"],
        }

    def _enforce_quality_gate(ctx: TenantContext, gate_type: str, target_type: str, target_id: str, *, required: bool = False) -> None:
        quality = _latest_quality(ctx, target_type, target_id)
        if quality["overall_score"] is None:
            if required:
                raise AuthorizationError(f"quality gate failed: {gate_type}")
            return
        scorecard = evaluation_runner.scorecard(ctx, str(quality["run_id"]))
        quality_gates.enforce(gate_type, scorecard)

    def _enforce_connector_publish_gate(
        ctx: TenantContext,
        manifest: PackageManifest,
        metadata: PackageMetadata,
        payload: dict,
    ) -> None:
        declared = set(manifest.connector_permissions)
        connector_like = {
            permission for permission in manifest.tool_permissions
            if permission.split(".", 1)[0] in {
                "gmail", "calendar", "github", "jira", "slack", "servicenow", "s3",
                "custom_http", "teams", "salesforce", "sharepoint",
            }
        }
        if not connector_like.issubset(declared):
            raise AuthorizationError("marketplace connector permissions are undeclared")
        minimum_trust = float(payload.get("minimum_connector_trust_score", 0.8))
        covered: set[str] = set()
        for requirement in manifest.connector_requirements:
            try:
                connector = enterprise_connectors.registry.get(ctx, requirement)
            except NotFoundError as exc:
                raise AuthorizationError("required connector is not registered") from exc
            requested = {
                permission for permission in declared
                if permission in set(connector.required_permissions)
            }
            covered.update(requested)
            if connector.trust_score < minimum_trust:
                raise AuthorizationError("required connector trust score is too low")
            if connector.risk_level in {"high", "critical"} and not metadata.high_risk_approved:
                raise AuthorizationError("risky connector requires marketplace review")
        if declared - covered:
            raise AuthorizationError("connector permissions exceed declared connector manifests")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield

    common_error_responses = {
        400: {"description": "Validation error"},
        401: {"description": "Authentication failure"},
        403: {"description": "RBAC, tenant isolation, policy, or trust denial"},
        404: {"description": "Resource not found"},
        409: {"description": "Conflict, quota, approval, integrity, or state failure"},
        503: {"description": "Dependency unavailable"},
    }

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="AgentFabric production API with Postgres/migrations queue auth and billing integrations.",
        lifespan=lifespan,
        responses=common_error_responses,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

    auth_rate_buckets: dict[tuple[str, int], int] = defaultdict(int)

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        import uuid
        start = time.perf_counter()
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000)
        principal_id = getattr(getattr(request.state, "principal", None), "principal_id", None)
        client_ip = request.client.host if request.client else "unknown"
        if request.headers.get("X-Forwarded-For"):
            client_ip = request.headers.get("X-Forwarded-For").split(",")[0].strip()
        try:
            from agentfabric.observability import get_logger
            log = get_logger("http")
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
                request_id=request_id,
                principal_id=principal_id,
            )
        except Exception:
            pass
        response.headers["X-Request-ID"] = request_id
        return response

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.middleware("http")
    async def rate_limit_auth_middleware(request: Request, call_next):
        if request.url.path not in {"/auth/principals/register", "/auth/token/issue"}:
            return await call_next(request)
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        minute_bucket = int(time.time() // 60)
        key = (client_ip, minute_bucket)
        auth_rate_buckets[key] += 1
        if auth_rate_buckets[key] > settings.rate_limit_auth_per_minute:
            return JSONResponse(status_code=429, content={"detail": "too many auth attempts"})
        to_drop = [k for k in list(auth_rate_buckets) if minute_bucket - (k[1]) > 1]
        for k in to_drop:
            auth_rate_buckets.pop(k, None)
        return await call_next(request)

    @app.exception_handler(AuthorizationError)
    async def _handle_authz_error(_: Request, exc: AuthorizationError):
        return domain_exception_response(exc)

    @app.exception_handler(NotFoundError)
    async def _handle_not_found(_: Request, exc: NotFoundError):
        return domain_exception_response(exc)

    @app.exception_handler(ConflictError)
    async def _handle_conflict(_: Request, exc: ConflictError):
        return domain_exception_response(exc)

    @app.exception_handler(ValidationError)
    async def _handle_validation(_: Request, exc: ValidationError):
        return domain_exception_response(exc)

    @app.exception_handler(AgentFabricError)
    async def _handle_agentfabric(_: Request, exc: AgentFabricError):
        return domain_exception_response(exc)

    @app.exception_handler(HTTPException)
    async def _handle_http_exception(_: Request, exc: HTTPException):
        return http_exception_response(exc)

    def get_db():
        db = session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        unauthenticated_paths = {
            "/",
            "/health",
            "/ready",
            "/favicon.ico",
            "/auth/principals/register",
            "/auth/token/issue",
            "/billing/webhooks/stripe",
            "/openapi.json",
            "/docs",
            "/redoc",
        }
        if settings.metrics_public:
            unauthenticated_paths = unauthenticated_paths | {"/metrics"}
        if request.url.path in unauthenticated_paths:
            return await call_next(request)
        try:
            token = AuthService.parse_bearer_header(request.headers.get("Authorization"))
            with session_factory() as db:
                request.state.principal = auth.authenticate(db, token)
            return await call_next(request)
        except HTTPException as exc:
            return http_exception_response(exc)

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        timer = HTTP_REQUEST_LATENCY.labels(request.method, request.url.path).time()
        with timer:
            response = await call_next(request)
        HTTP_REQUEST_COUNT.labels(request.method, request.url.path, str(response.status_code)).inc()
        return response

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health():
        return HealthResponse()

    @app.get("/health/persistence", tags=["system"])
    def persistence_health(request: Request):
        require_scopes(request, ["persistence.read"])
        health_result = durable_store.health()
        health_result["schema_version"] = migration_result["current_version"]
        return health_result

    @app.get("/health/runtime", tags=["system"])
    def runtime_health(request: Request):
        require_scopes(request, ["runtime.jobs.read"])
        return cloud_runtime.health()

    @app.get("/health/workers", tags=["system"])
    def workers_health(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.read"])
        workers = cloud_runtime.workers.list(None if ctx.is_global_admin else ctx.tenant_id)
        return {"status": "ok", "items": [worker.as_dict() for worker in workers], "total": len(workers)}

    @app.get("/health/queues", tags=["system"])
    def queues_health(request: Request):
        require_scopes(request, ["runtime.jobs.read"])
        return cloud_queue.health()

    @app.get("/ready", tags=["system"])
    def ready(db: Session = Depends(get_db)):
        try:
            db.execute(text("SELECT 1"))
        except Exception:
            raise HTTPException(status_code=503, detail="database unavailable")
        if settings.redis_url.startswith("redis://"):
            try:
                import redis as redis_client
                r = redis_client.from_url(settings.redis_url)
                r.ping()
            except Exception:
                raise HTTPException(status_code=503, detail="redis unavailable")
        return {"status": "ready"}

    @app.get("/", tags=["system"])
    def root():
        return {
            "service": settings.app_name,
            "message": "API is running. Open /docs for interactive API documentation.",
            "docs": "/docs",
            "health": "/health",
            "ready": "/ready",
            "openapi": "/openapi.json",
        }

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    def _principal_count(db: Session) -> int:
        return int(db.execute(select(func.count(Principal.principal_id))).scalar_one())

    def _require_bootstrap_token(request: Request) -> None:
        if not settings.bootstrap_token:
            raise HTTPException(status_code=503, detail="bootstrap token is not configured")
        provided = request.headers.get("X-AgentFabric-Bootstrap-Token")
        if provided != settings.bootstrap_token:
            raise HTTPException(status_code=401, detail="invalid bootstrap token")

    @app.post("/auth/principals/register", tags=["auth"])
    def register_principal(payload: RegisterPrincipalRequest, request: Request, db: Session = Depends(get_db)):
        if _principal_count(db) == 0:
            _require_bootstrap_token(request)
        else:
            token = AuthService.parse_bearer_header(request.headers.get("Authorization"))
            principal = auth.authenticate(db, token)
            if "auth.admin" not in principal.scopes:
                raise HTTPException(status_code=403, detail="insufficient scope")
            if principal.tenant_id != payload.tenant_id:
                raise HTTPException(status_code=403, detail="cross-tenant registration denied")
        principal = auth.register_principal(
            db,
            principal_id=payload.principal_id,
            tenant_id=payload.tenant_id,
            principal_type=payload.principal_type,
            scopes=payload.scopes,
            role=payload.role,
        )
        return {"principal_id": principal.principal_id, "tenant_id": principal.tenant_id, "role": principal.role}

    @app.post("/auth/token/issue", response_model=TokenResponse, tags=["auth"])
    def issue_token(payload: IssueTokenRequest, request: Request, db: Session = Depends(get_db)):
        target = db.get(Principal, payload.principal_id)
        if target is None:
            raise HTTPException(status_code=404, detail="principal not found")
        auth_header = request.headers.get("Authorization")
        if auth_header:
            token = AuthService.parse_bearer_header(auth_header)
            caller = auth.authenticate(db, token)
            if "auth.token.issue" not in caller.scopes:
                raise HTTPException(status_code=403, detail="insufficient scope")
            if caller.tenant_id != target.tenant_id:
                raise HTTPException(status_code=403, detail="cross-tenant token issuance denied")
        else:
            _require_bootstrap_token(request)
        token, ttl = auth.issue_token(db, principal_id=payload.principal_id, ttl_seconds=payload.ttl_seconds)
        return TokenResponse(access_token=token, expires_in=ttl)

    @app.post("/auth/token/rotate", response_model=TokenResponse, tags=["auth"])
    def rotate_token(payload: RotateTokenRequest, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, [])
        token = AuthService.parse_bearer_header(request.headers.get("Authorization"))
        new_token, ttl = auth.rotate_token(db, bearer_token=token, ttl_seconds=payload.ttl_seconds)
        return TokenResponse(access_token=new_token, expires_in=ttl)

    @app.post("/tenants", tags=["tenants"])
    def tenants_create(payload: dict, request: Request):
        principal = require_scopes(request, ["tenant.manage"])
        organization_id = payload.get("organization_id") or payload["tenant_id"]
        tenant = tenant_service.create_tenant(
            tenant_id=payload["tenant_id"],
            organization_id=organization_id,
            name=payload.get("name", payload["tenant_id"]),
            created_by=principal.principal_id,
            billing_plan=payload.get("billing_plan", "dev"),
        )
        membership_service.add(
            Membership(
                principal_id=principal.principal_id,
                tenant_id=tenant.tenant_id,
                organization_id=tenant.organization_id,
                role="owner",
                member_type=principal.principal_type,
                created_by=principal.principal_id,
            ),
            actor_member_type=principal.principal_type,
            actor_role="owner",
        )
        event_store.append("tenant.created", tenant.tenant_id, tenant.as_dict())
        plan_revenue = {"dev": 0.0, "team": 500.0, "enterprise": 5000.0, "internal": 0.0}.get(tenant.billing_plan, 0.0)
        revenue = revenue_tracker.record(tenant.tenant_id, "subscription", amount=plan_revenue, source_id=tenant.billing_plan)
        event_store.append("economics.revenue.recorded", revenue.event_id, revenue.as_dict())
        return tenant.as_dict()

    @app.get("/tenants", tags=["tenants"])
    def tenants_list(request: Request):
        principal = require_scopes(request, ["tenant.manage"])
        items = tenant_service.list_for_principal(
            principal.tenant_id,
            global_admin="tenant.global" in principal.scopes,
        )
        return {"items": [item.as_dict() for item in items], "total": len(items)}

    @app.get("/tenants/{tenant_id}", tags=["tenants"])
    def tenants_get(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["tenant.manage"])
        tenant = tenant_service.get(tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant not found")
        return tenant.as_dict()

    @app.post("/tenants/{tenant_id}/teams", tags=["tenants"])
    def tenant_team_create(tenant_id: str, payload: dict, request: Request):
        principal = _assert_tenant_access(request, tenant_id, ["team.manage"])
        tenant = tenant_service.get(tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant not found")
        team = Team(
            team_id=payload.get("team_id") or f"team-{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            organization_id=tenant.organization_id,
            name=payload["name"],
            created_by=principal.principal_id,
        )
        durable_store.put("teams", team.team_id, team.as_dict())
        event_store.append("team.created", team.team_id, team.as_dict())
        return team.as_dict()

    @app.get("/tenants/{tenant_id}/teams", tags=["tenants"])
    def tenant_teams_list(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["team.manage"])
        items = durable_store.list_tenant("teams", tenant_id)
        return {"items": items, "total": len(items)}

    @app.post("/tenants/{tenant_id}/members", tags=["tenants"])
    def tenant_member_add(tenant_id: str, payload: dict, request: Request):
        principal = _assert_tenant_access(request, tenant_id, ["members.manage"])
        tenant = tenant_service.get(tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant not found")
        try:
            membership = membership_service.add(
                Membership(
                    principal_id=payload["principal_id"],
                    tenant_id=tenant_id,
                    organization_id=tenant.organization_id,
                    role=payload["role"],
                    member_type=payload.get("member_type", "user"),
                    team_id=payload.get("team_id"),
                    created_by=principal.principal_id,
                ),
                actor_member_type=principal.principal_type,
                actor_role="owner" if "tenant.manage" in principal.scopes else "admin",
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        event_store.append("member.added", membership.membership_id, membership.as_dict())
        return membership.as_dict()

    @app.get("/tenants/{tenant_id}/members", tags=["tenants"])
    def tenant_members_list(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["members.manage"])
        items = [item.as_dict() for item in membership_service.list_for_tenant(tenant_id)]
        return {"items": items, "total": len(items)}

    @app.get("/tenants/{tenant_id}/usage", tags=["tenants"])
    def tenant_usage(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["usage.read"])
        persisted = metering.aggregate(tenant_id)
        reconstructed = metering.reconstruct_from_events(tenant_id, event_store)
        combined = dict(reconstructed)
        for key, value in persisted.items():
            combined[key] = combined.get(key, 0) + value
        return {"tenant_id": tenant_id, "usage": combined}

    @app.get("/tenants/{tenant_id}/quotas", tags=["tenants"])
    def tenant_quotas(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["quotas.read"])
        return {"tenant_id": tenant_id, "limits": _tenant_policy(tenant_id).as_dict(), "usage": quota_tracker.usage(tenant_id).as_dict()}

    @app.patch("/tenants/{tenant_id}/quotas", tags=["tenants"])
    def tenant_quotas_update(tenant_id: str, payload: dict, request: Request):
        _assert_tenant_access(request, tenant_id, ["quotas.manage"])
        policy = QuotaPolicy.from_dict(payload)
        durable_store.put("quota_policies", tenant_id, {"tenant_id": tenant_id, **policy.as_dict()})
        event_store.append("quota.updated", tenant_id, {"tenant_id": tenant_id, "limits": policy.as_dict()})
        return {"tenant_id": tenant_id, "limits": policy.as_dict()}

    @app.get("/tenants/{tenant_id}/billing", tags=["tenants"])
    def tenant_billing_get(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["billing.read"])
        tenant = tenant_service.get(tenant_id)
        plan_id = tenant.billing_plan if tenant else "dev"
        return {"tenant_id": tenant_id, "plan": get_billing_plan(plan_id).as_dict()}

    @app.patch("/tenants/{tenant_id}/billing", tags=["tenants"])
    def tenant_billing_update(tenant_id: str, payload: dict, request: Request):
        _assert_tenant_access(request, tenant_id, ["billing.manage"])
        target_plan = get_billing_plan(payload["billing_plan"])
        usage = quota_tracker.usage(tenant_id)
        for key, limit in target_plan.quota_policy.as_dict().items():
            if usage.get(key) > limit:
                raise HTTPException(status_code=409, detail=f"billing plan downgrade violates current usage: {key}")
        tenant = tenant_service.update_billing_plan(tenant_id, target_plan.plan_id)
        event_store.append("billing.plan_updated", tenant_id, {"tenant_id": tenant_id, "billing_plan": target_plan.plan_id})
        return {"tenant_id": tenant_id, "plan": get_billing_plan(tenant.billing_plan).as_dict()}

    @app.get("/economics/tenants/{tenant_id}", tags=["economics"])
    def economics_tenant(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["economics.read"])
        return tenant_profitability.report(tenant_id)

    @app.get("/economics/tenants/{tenant_id}/costs", tags=["economics"])
    def economics_tenant_costs(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["economics.read"])
        events = [event.as_dict() for event in cost_tracker.list_for_tenant(tenant_id)]
        return {"tenant_id": tenant_id, "total_cost": cost_tracker.total(tenant_id), "items": events}

    @app.get("/economics/tenants/{tenant_id}/revenue", tags=["economics"])
    def economics_tenant_revenue(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["economics.read"])
        events = [event.as_dict() for event in revenue_tracker.list_for_tenant(tenant_id)]
        return {"tenant_id": tenant_id, "total_revenue": revenue_tracker.total(tenant_id), "items": events}

    @app.get("/economics/tenants/{tenant_id}/margin", tags=["economics"])
    def economics_tenant_margin(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["economics.read"])
        return margin_analyzer.tenant_margin(tenant_id).as_dict()

    @app.get("/economics/packages/{package_id}/revenue", tags=["economics"])
    def economics_package_revenue(package_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["economics.read"])
        return package_revenue.report(package_id, None if ctx.is_global_admin else ctx.tenant_id)

    @app.get("/economics/runtime/costs", tags=["economics"])
    def economics_runtime_costs(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["economics.read"])
        items = [event.as_dict() for event in cost_tracker.list_for_tenant(ctx.tenant_id)]
        runtime_items = [item for item in items if item["category"] in {"queue_worker_runtime", "agent_run", "workflow_run", "tool_execution", "connector_sync", "evaluation_run"}]
        return {"tenant_id": ctx.tenant_id, "items": runtime_items, "total_cost": round(sum(float(item["amount"]) for item in runtime_items), 4)}

    @app.patch("/economics/tenants/{tenant_id}/spend-limits", tags=["economics"])
    def economics_spend_limits(tenant_id: str, payload: dict, request: Request):
        _assert_tenant_access(request, tenant_id, ["economics.manage"])
        limits = cost_tracker.set_spend_limits(tenant_id, {key: float(value) for key, value in payload.items()})
        event_store.append("economics.spend_limit.updated", tenant_id, limits)
        return limits

    @app.get("/tenants/{tenant_id}/audit-export", tags=["tenants"])
    def tenant_audit_export(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["audit.export"])
        events = [event.as_dict() for event in event_store.replay() if event.payload.get("tenant_id") == tenant_id]
        memory = [item for item in durable_store.list_tenant("runtime_memory", tenant_id)]
        usage = [item for item in durable_store.list_tenant("usage_events", tenant_id)]
        decisions = [item for item in durable_store.list_tenant("governance_decision_records", tenant_id)]
        return {
            "tenant_id": tenant_id,
            "events": events,
            "memory_operations": [{"memory_id": item["memory_id"], "classification": item["classification"]} for item in memory],
            "usage_history": usage,
            "governance_decision_records": decisions,
        }

    @app.post("/registry/publish", response_model=PackageResponse, tags=["registry"])
    def publish_package(payload: PublishPackageRequest, request: Request, db: Session = Depends(get_db)):
        _tenant_context(request)
        principal = require_scopes(request, ["registry.publish"], tenant_id=payload.namespace)
        if principal.principal_id != payload.namespace:
            raise HTTPException(status_code=403, detail="principal cannot publish to this namespace")
        service = PackageService(db, signing_verifier=signing_verifier)
        package = service.publish(
            namespace=payload.namespace,
            package_id=payload.package_id,
            version=payload.version,
            category=payload.category,
            permissions=payload.permissions,
            manifest=payload.manifest,
            payload=payload.payload.encode("utf-8"),
            signature=payload.signature,
            signer_id=payload.signer_id,
        )
        metering.record(principal.tenant_id, "marketplace_publishes", metadata={"package_id": payload.package_id})
        revenue = revenue_tracker.record(principal.tenant_id, "marketplace", amount=pricing_policy.per_marketplace_package, source_id=payload.package_id, package_id=payload.package_id)
        event_store.append("economics.revenue.recorded", revenue.event_id, revenue.as_dict())
        return PackageResponse(
            fqid=f"{package.namespace}/{package.package_id}:{package.version}",
            payload_digest=package.payload_digest,
        )

    @app.get("/registry/list", response_model=ListPackagesResponse, tags=["registry"])
    def list_packages(
        request: Request,
        query: str | None = None,
        category: str | None = None,
        permission: list[str] | None = None,
        page: int = 1,
        page_size: int = 20,
        db: Session = Depends(get_db),
    ):
        principal = require_scopes(request, ["registry.read"])
        _tenant_context(request)
        service = PackageService(db, signing_verifier=signing_verifier)
        result = service.list_packages(
            query=query,
            category=category,
            required_permissions=set(permission or []),
            page=page,
            page_size=page_size,
            namespace_filter=principal.tenant_id if "tenant.global" not in principal.scopes else None,
        )
        return ListPackagesResponse(**result)

    @app.post("/registry/install", tags=["registry"])
    def install_package(payload: InstallPackageRequest, request: Request, db: Session = Depends(get_db)):
        _tenant_context(request)
        limit_enforcer.consume(payload.tenant_id, _tenant_policy(payload.tenant_id), "marketplace_installs")
        require_scopes(request, ["registry.install"], tenant_id=payload.tenant_id)
        service = PackageService(db, signing_verifier=signing_verifier)
        install = service.install(
            tenant_id=payload.tenant_id,
            user_id=payload.user_id,
            namespace=payload.namespace,
            package_id=payload.package_id,
            version=payload.version,
        )
        metering.record(payload.tenant_id, "marketplace_installs", metadata={"package_fqid": install.package_fqid})
        return {"id": install.id, "package_fqid": install.package_fqid}

    @app.post("/marketplace/packages", tags=["marketplace"])
    def marketplace_package_publish(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.publish"])
        _marketplace_plan_allows(ctx, "publish")
        manifest = _manifest_from_payload(payload, ctx)
        metadata = PackageMetadata.from_dict(payload.get("metadata", {}))
        try:
            operational_intelligence.enforce_marketplace_gate(
                ctx,
                manifest.agent_identity_id,
                manifest.version,
                minimum_quality=float(payload.get("minimum_quality", 0.8)),
            )
            _enforce_quality_gate(
                ctx,
                "package_publish",
                "marketplace_package",
                manifest.package_id,
                required=bool(payload.get("quality_gate_required", False)),
            )
            _enforce_connector_publish_gate(ctx, manifest, metadata, payload)
        except AuthorizationError as exc:
            event_store.append(
                "marketplace.package.rejected",
                manifest.package_id,
                {"tenant_id": ctx.tenant_id, "package_id": manifest.package_id, "reason": str(exc)},
            )
            raise HTTPException(status_code=403, detail=str(exc))
        signing_key = SigningKey(publisher_id=ctx.tenant_id, secret=payload.get("signing_secret", "local-dev-secret"))
        trusted_publishers.trust(ctx.tenant_id, signing_key.fingerprint)
        signature = payload.get("signature") or PackageSignature.sign(manifest.manifest_hash(), signing_key).signature
        try:
            package = marketplace_publish.publish(
                manifest=manifest,
                metadata=metadata,
                signature=signature,
                signing_key=signing_key,
            )
        except ValidationError as exc:
            event_store.append(
                "marketplace.package.rejected",
                manifest.package_id,
                {"tenant_id": ctx.tenant_id, "package_id": manifest.package_id, "reason": str(exc)},
            )
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "marketplace_publishes", metadata={"package_id": package.package_id})
        revenue = revenue_tracker.record(ctx.tenant_id, "marketplace", amount=pricing_policy.per_marketplace_package, source_id=package.package_id, package_id=package.package_id)
        event_store.append("economics.revenue.recorded", revenue.event_id, revenue.as_dict())
        return package.as_dict()

    @app.get("/marketplace/packages", tags=["marketplace"])
    def marketplace_packages_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.read"])
        items = [package.as_dict() for package in marketplace_registry.list_packages(ctx.tenant_id)]
        return {"items": items, "total": len(items)}

    @app.get("/marketplace/packages/{package_id}", tags=["marketplace"])
    def marketplace_package_get(package_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.read"])
        package = marketplace_registry.get(package_id)
        if package.metadata.private and package.manifest.publisher_tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=403, detail="cross-tenant marketplace access denied")
        return package.as_dict()

    @app.post("/marketplace/packages/{package_id}/versions", tags=["marketplace"])
    def marketplace_package_version(package_id: str, payload: dict, request: Request):
        payload = {**payload, "package_id": package_id}
        return marketplace_package_publish(payload, request)

    @app.post("/marketplace/packages/{package_id}/install", tags=["marketplace"])
    def marketplace_package_install(package_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.install"])
        _marketplace_plan_allows(ctx, "install")
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "marketplace_installs")
        try:
            install = marketplace_install.install(
                tenant_id=ctx.tenant_id,
                package_id=package_id,
                version=payload.get("version"),
                approved_permissions=bool(payload.get("approved_permissions", False)),
            )
        except (AuthorizationError, ValidationError) as exc:
            raise HTTPException(status_code=403 if isinstance(exc, AuthorizationError) else 400, detail=str(exc))
        metering.record(ctx.tenant_id, "marketplace_installs", metadata={"package_id": package_id})
        revenue = revenue_tracker.record(ctx.tenant_id, "marketplace", amount=pricing_policy.per_marketplace_package, source_id=package_id, package_id=package_id)
        event_store.append("economics.revenue.recorded", revenue.event_id, revenue.as_dict())
        return install

    @app.post("/marketplace/packages/{package_id}/uninstall", tags=["marketplace"])
    def marketplace_package_uninstall(package_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.install"])
        try:
            return marketplace_install.uninstall(tenant_id=ctx.tenant_id, package_id=package_id)
        except ValidationError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/marketplace/packages/{package_id}/upgrade", tags=["marketplace"])
    def marketplace_package_upgrade(package_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.install"])
        try:
            result = marketplace_install.upgrade(tenant_id=ctx.tenant_id, package_id=package_id, version=payload.get("version"))
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "marketplace_upgrades", metadata={"package_id": package_id})
        return result

    @app.post("/marketplace/packages/{package_id}/rollback", tags=["marketplace"])
    def marketplace_package_rollback(package_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.install"])
        try:
            result = marketplace_install.rollback(
                tenant_id=ctx.tenant_id,
                package_id=package_id,
                version=payload["version"],
                admin_override=bool(payload.get("admin_override", False)),
            )
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "marketplace_rollbacks", metadata={"package_id": package_id})
        return result

    @app.get("/marketplace/packages/{package_id}/risk", tags=["marketplace"])
    def marketplace_package_risk(package_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.read"])
        package = marketplace_registry.get(package_id)
        if package.metadata.private and package.manifest.publisher_tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=403, detail="cross-tenant marketplace access denied")
        return MarketplaceScanner().scan(package, marketplace_registry.available_by_id())

    @app.get("/marketplace/packages/{package_id}/quality", tags=["marketplace"])
    def marketplace_package_quality(package_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["evaluations.read"])
        return _latest_quality(ctx, "marketplace_package", package_id)

    @app.get("/marketplace/installed", tags=["marketplace"])
    def marketplace_installed(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.read"])
        return {"items": marketplace_install.list_installed(ctx.tenant_id)}

    @app.post("/marketplace/packages/{package_id}/reviews", tags=["marketplace"])
    def marketplace_package_review(package_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.review"])
        marketplace_install.verify_runtime_entitlement(tenant_id=ctx.tenant_id, package_id=package_id)
        review = marketplace_reviews.submit(
            PackageReview(
                tenant_id=ctx.tenant_id,
                package_id=package_id,
                rating=int(payload["rating"]),
                review=payload.get("review", ""),
                abuse_report=bool(payload.get("abuse_report", False)),
            )
        )
        event_store.append(
            "marketplace.review.submitted",
            package_id,
            {"tenant_id": ctx.tenant_id, "package_id": package_id, "rating": review.rating},
        )
        if review.abuse_report:
            event_store.append(
                "marketplace.abuse_report.submitted",
                package_id,
                {"tenant_id": ctx.tenant_id, "package_id": package_id},
            )
        return review.as_dict()

    @app.get("/marketplace/publishers/{publisher_id}/reputation", tags=["marketplace"])
    def marketplace_publisher_reputation(publisher_id: str, request: Request):
        _tenant_context(request)
        require_scopes(request, ["marketplace.read"])
        return publisher_reputation.reputation(publisher_id)

    @app.post("/governance/orgs", tags=["governance"])
    def governance_org_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.manage"])
        org = governance.create_org(
            AgentOrganization(
                org_id=payload.get("org_id") or f"gov-org-{uuid4().hex[:12]}",
                tenant_id=ctx.tenant_id,
                organization_id=ctx.organization_id,
                name=payload["name"],
                authority_boundaries=tuple(payload.get("authority_boundaries", ())),
                allowed_workflow_types=tuple(payload.get("allowed_workflow_types", ())),
                budget_limits=dict(payload.get("budget_limits", {})),
                created_by=ctx.principal_id,
            )
        )
        return org.as_dict()

    @app.get("/governance/orgs", tags=["governance"])
    def governance_orgs_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.read"])
        items = [org.as_dict() for org in governance.list_orgs(ctx.tenant_id)]
        return {"items": items, "total": len(items)}

    @app.get("/governance/orgs/{org_id}", tags=["governance"])
    def governance_org_get(org_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.read"])
        org = governance.get_org(org_id)
        _assert_governance_tenant(ctx, org.as_dict())
        return org.as_dict()

    @app.post("/governance/orgs/{org_id}/teams", tags=["governance"])
    def governance_team_create(org_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.manage"])
        org = governance.get_org(org_id)
        _assert_governance_tenant(ctx, org.as_dict())
        team = governance.create_team(
            AgentTeam(
                team_id=payload.get("team_id") or f"gov-team-{uuid4().hex[:12]}",
                org_id=org_id,
                tenant_id=ctx.tenant_id,
                organization_id=ctx.organization_id,
                name=payload["name"],
                roles={str(agent_id): str(role) for agent_id, role in dict(payload.get("roles", {})).items()},
                created_by=ctx.principal_id,
            )
        )
        return team.as_dict()

    @app.post("/governance/orgs/{org_id}/charter", tags=["governance"])
    def governance_charter_update(org_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.manage"])
        org = governance.get_org(org_id)
        _assert_governance_tenant(ctx, org.as_dict())
        charter = governance.update_charter(
            Charter(
                org_id=org_id,
                tenant_id=ctx.tenant_id,
                organization_id=ctx.organization_id,
                purpose=payload["purpose"],
                authority_boundaries=tuple(payload.get("authority_boundaries", ())),
                allowed_workflow_types=tuple(payload.get("allowed_workflow_types", ())),
                escalation_requirements=tuple(payload.get("escalation_requirements", ())),
                budget_limits=dict(payload.get("budget_limits", {})),
                updated_by=ctx.principal_id,
            )
        )
        return charter.as_dict()

    @app.post("/governance/proposals", tags=["governance"])
    def governance_proposal_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.propose"])
        target_org_id = payload["target_org_id"]
        org = governance.get_org(target_org_id)
        _assert_governance_tenant(ctx, org.as_dict())
        proposal = Proposal(
            proposal_id=payload.get("proposal_id") or f"proposal-{uuid4().hex[:12]}",
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
            proposing_agent_id=payload["proposing_agent_id"],
            target_org_id=target_org_id,
            target_team_id=payload.get("target_team_id"),
            action_type=payload["action_type"],
            risk_level=payload.get("risk_level", "medium"),
            required_approvals=int(payload.get("required_approvals", 1)),
            veil_trust_metadata_ref=payload.get("veil_trust_metadata_ref"),
            consensus_mode=payload.get("consensus_mode", "majority"),
            created_by=ctx.principal_id,
        )
        try:
            created = governance.create_proposal(proposal, assigned_reviewer=payload.get("assigned_reviewer") or ctx.principal_id)
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        metering.record(ctx.tenant_id, "governance_proposals", metadata={"proposal_id": created.proposal_id})
        return created.as_dict()

    @app.get("/governance/proposals", tags=["governance"])
    def governance_proposals_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.read"])
        items = [proposal.as_dict() for proposal in governance.list_proposals(ctx.tenant_id)]
        return {"items": items, "total": len(items)}

    @app.get("/governance/proposals/{proposal_id}", tags=["governance"])
    def governance_proposal_get(proposal_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.read"])
        proposal = governance.get_proposal(proposal_id)
        _assert_governance_tenant(ctx, proposal.as_dict())
        return proposal.as_dict()

    @app.post("/governance/proposals/{proposal_id}/vote", tags=["governance"])
    def governance_proposal_vote(proposal_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.vote"])
        proposal = governance.get_proposal(proposal_id)
        _assert_governance_tenant(ctx, proposal.as_dict())
        gov_policy = _governance_policy(ctx)
        required_roles: list[str] = list(payload.get("required_roles", ()))
        if proposal.action_type in gov_policy.security_required_actions and "security_reviewer" not in required_roles:
            required_roles.append("security_reviewer")
        if proposal.action_type in gov_policy.compliance_required_actions and "compliance_reviewer" not in required_roles:
            required_roles.append("compliance_reviewer")
        vote = Vote(
            proposal_id=proposal_id,
            tenant_id=ctx.tenant_id,
            voter_agent_id=payload["voter_agent_id"],
            voter_role=payload["voter_role"],
            vote=payload["vote"],
            weight=int(payload.get("weight", 1)),
            reason=payload.get("reason", ""),
        )
        try:
            saved, result, updated = governance.cast_vote(
                vote,
                policy=ConsensusPolicy(
                    mode=proposal.consensus_mode,
                    threshold=float(payload.get("threshold", 2 / 3 if proposal.consensus_mode == "supermajority" else 0.5)),
                    required_roles=tuple(required_roles),
                    required_approvals=proposal.required_approvals,
                ),
                governance_policy=gov_policy,
            )
        except (AuthorizationError, ConflictError, ValidationError) as exc:
            raise HTTPException(status_code=403 if isinstance(exc, AuthorizationError) else 409, detail=str(exc))
        return {"vote": saved.as_dict(), "consensus": result.as_dict(), "proposal": updated.as_dict()}

    @app.post("/governance/proposals/{proposal_id}/execute", tags=["governance"])
    def governance_proposal_execute(proposal_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.execute"])
        proposal = governance.get_proposal(proposal_id)
        _assert_governance_tenant(ctx, proposal.as_dict())
        gov_policy = _governance_policy(ctx)
        require_human = proposal.consensus_mode == "human_required" or gov_policy.requires_human(proposal.risk_level)
        try:
            record = governance.execute(
                proposal_id,
                action_payload={
                    "action_type": proposal.action_type,
                    "approved_by": ctx.principal_id,
                    "result": payload.get("result", "executed"),
                    "target_ref": payload.get("target_ref"),
                },
                require_human=require_human,
            )
        except (AuthorizationError, ConflictError) as exc:
            raise HTTPException(status_code=403 if isinstance(exc, AuthorizationError) else 409, detail=str(exc))
        metering.record(ctx.tenant_id, "governed_actions", metadata={"proposal_id": proposal_id})
        return record.as_dict()

    @app.get("/governance/proposals/{proposal_id}/decision-record", tags=["governance"])
    def governance_decision_record(proposal_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.read"])
        record = governance.decision_record(proposal_id)
        _assert_governance_tenant(ctx, record.as_dict())
        return record.as_dict()

    @app.get("/governance/approvals", tags=["governance"])
    def governance_approvals_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.approve"])
        items = [approval.as_dict() for approval in governance_approvals.list(ctx.tenant_id)]
        return {"items": items, "total": len(items)}

    def _resolve_governance_approval(approval_id: str, request: Request, status: str, reason: str):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.approve"])
        approval = governance_approvals.get(approval_id)
        if approval is None:
            raise HTTPException(status_code=404, detail="approval not found")
        _assert_governance_tenant(ctx, approval.as_dict())
        try:
            resolved = governance_approvals.resolve(approval_id, status=status, reason=reason)
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        event_type = {
            "approved": "governance.human_approval.granted",
            "rejected": "governance.human_approval.rejected",
            "escalated": "governance.human_approval.escalated",
        }[status]
        event_store.append(event_type, approval.proposal_id, resolved.as_dict())
        proposal = governance.get_proposal(approval.proposal_id)
        if status == "approved":
            updated = proposal.with_status(ProposalStatus.APPROVED.value)
        elif status == "rejected":
            updated = proposal.with_status(ProposalStatus.REJECTED.value)
        else:
            updated = proposal.with_status(ProposalStatus.ESCALATED.value)
        durable_store.put("governance_proposals", updated.proposal_id, updated.as_dict())
        return resolved.as_dict()

    @app.post("/governance/approvals/{approval_id}/approve", tags=["governance"])
    def governance_approval_approve(approval_id: str, payload: dict, request: Request):
        return _resolve_governance_approval(approval_id, request, "approved", payload.get("reason", "approved"))

    @app.post("/governance/approvals/{approval_id}/reject", tags=["governance"])
    def governance_approval_reject(approval_id: str, payload: dict, request: Request):
        return _resolve_governance_approval(approval_id, request, "rejected", payload.get("reason", "rejected"))

    @app.post("/governance/approvals/{approval_id}/escalate", tags=["governance"])
    def governance_approval_escalate(approval_id: str, payload: dict, request: Request):
        return _resolve_governance_approval(approval_id, request, "escalated", payload.get("reason", "escalated"))

    @app.post("/federation/orgs", tags=["federation"])
    def federation_org_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        org = federation.create_org(
            FederatedOrg(
                tenant_id=ctx.tenant_id,
                organization_id=ctx.organization_id,
                remote_org_id=payload["remote_org_id"],
                name=payload.get("name", payload["remote_org_id"]),
                endpoint=payload.get("endpoint", ""),
                public_key=payload.get("public_key", ""),
                created_by=ctx.principal_id,
                org_id=payload.get("org_id") or f"fed-org-{uuid4().hex[:12]}",
            )
        )
        return org.as_dict()

    @app.get("/federation/orgs", tags=["federation"])
    def federation_orgs_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.read"])
        items = [org.as_dict() for org in federation.registry.list_orgs(ctx.tenant_id)]
        return {"items": items, "total": len(items)}

    @app.get("/federation/orgs/{org_id}", tags=["federation"])
    def federation_org_get(org_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.read"])
        org = federation.registry.get_org(org_id)
        _assert_governance_tenant(ctx, org.as_dict())
        return org.as_dict()

    @app.post("/federation/agreements", tags=["federation"])
    def federation_agreement_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        expires_at = datetime.fromisoformat(payload["expires_at"]) if payload.get("expires_at") else None
        kwargs = {"expires_at": expires_at} if expires_at else {}
        try:
            agreement = federation.create_agreement(
                TrustAgreement(
                    tenant_id=ctx.tenant_id,
                    organization_id=ctx.organization_id,
                    remote_org_id=payload["remote_org_id"],
                    created_by=ctx.principal_id,
                    allowed_capabilities=tuple(payload.get("allowed_capabilities", ())),
                    denied_capabilities=tuple(payload.get("denied_capabilities", ())),
                    permitted_data_classes=tuple(payload.get("permitted_data_classes", ("public", "internal"))),
                    allowed_workflow_types=tuple(payload.get("allowed_workflow_types", ())),
                    **kwargs,
                )
            )
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return agreement.as_dict()

    @app.get("/federation/agreements", tags=["federation"])
    def federation_agreements_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.read"])
        items = [agreement.as_dict() for agreement in federation.registry.list_agreements(ctx.tenant_id)]
        return {"items": items, "total": len(items)}

    @app.get("/federation/agreements/{agreement_id}", tags=["federation"])
    def federation_agreement_get(agreement_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.read"])
        agreement = federation.registry.get_agreement(agreement_id)
        _assert_governance_tenant(ctx, agreement.as_dict())
        return agreement.as_dict()

    @app.post("/federation/agreements/{agreement_id}/activate", tags=["federation"])
    def federation_agreement_activate(agreement_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.manage"])
        agreement = federation.registry.get_agreement(agreement_id)
        _assert_governance_tenant(ctx, agreement.as_dict())
        try:
            return federation.activate_agreement(agreement_id).as_dict()
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    @app.post("/federation/agreements/{agreement_id}/revoke", tags=["federation"])
    def federation_agreement_revoke(agreement_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.manage"])
        agreement = federation.registry.get_agreement(agreement_id)
        _assert_governance_tenant(ctx, agreement.as_dict())
        return federation.revoke_agreement(agreement_id, payload.get("reason", "revoked")).as_dict()

    def _remote_agent_from_payload(payload: dict, ctx: TenantContext) -> RemoteAgent:
        return RemoteAgent(
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
            remote_org_id=payload["remote_org_id"],
            remote_agent_id=payload["remote_agent_id"],
            name=payload.get("name", payload["remote_agent_id"]),
            capabilities=tuple(RemoteCapability.from_dict(item) for item in payload.get("capabilities", ())),
            reputation_score=float(payload.get("reputation_score", 1.0)),
            publisher_id=payload.get("publisher_id", ""),
            blocked=bool(payload.get("blocked", False)),
        )

    @app.post("/federation/capabilities/publish", tags=["federation"])
    def federation_capabilities_publish(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.manage"])
        agreement = federation.registry.get_agreement(payload["trust_agreement_id"])
        _assert_governance_tenant(ctx, agreement.as_dict())
        try:
            return federation.publish_capability(_remote_agent_from_payload(payload, ctx), agreement).as_dict()
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.get("/federation/capabilities", tags=["federation"])
    def federation_capabilities(request: Request, agreement_id: str, capability: str | None = None):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.read"])
        try:
            items = federation.discover(tenant_id=ctx.tenant_id, organization_id=ctx.organization_id, agreement_id=agreement_id, capability=capability)
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        return {"items": [item.as_dict() for item in items], "total": len(items)}

    @app.post("/federation/capabilities/import", tags=["federation"])
    def federation_capabilities_import(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.manage"])
        agreement = federation.registry.get_agreement(payload["trust_agreement_id"])
        _assert_governance_tenant(ctx, agreement.as_dict())
        try:
            return federation.import_capability(_remote_agent_from_payload(payload, ctx), agreement).as_dict()
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/federation/messages/send", tags=["federation"])
    def federation_message_send(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.message"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        signing_secret = payload.get("signing_secret", "local-federation-secret")
        agreement = federation.registry.get_agreement(payload["trust_agreement_id"])
        _assert_governance_tenant(ctx, agreement.as_dict())
        message = FederatedMessage.create(
            signing_secret=signing_secret,
            source_org_id=ctx.organization_id,
            source_tenant_id=ctx.tenant_id,
            destination_org_id=agreement.remote_org_id,
            destination_tenant_id=payload.get("destination_tenant_id", agreement.remote_org_id),
            source_agent_id=payload["source_agent_id"],
            destination_agent_id=payload["destination_agent_id"],
            trust_agreement_id=agreement.agreement_id,
            payload=dict(payload.get("payload", {})),
            veil_reference=payload.get("veil_reference", ""),
            ttl_seconds=int(payload.get("ttl_seconds", 300)),
            message_type=payload.get("message_type", "request"),
        )
        try:
            receipt = federation.send_message(message, signing_secret)
        except (AuthorizationError, ValidationError) as exc:
            raise HTTPException(status_code=403 if isinstance(exc, AuthorizationError) else 400, detail=str(exc))
        return {"message": message.as_dict(), "receipt": receipt.as_dict()}

    @app.get("/federation/messages/{message_id}", tags=["federation"])
    def federation_message_get(message_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.read"])
        message = federation.get_message(message_id)
        if message.source_tenant_id != ctx.tenant_id and message.destination_tenant_id != ctx.tenant_id and not ctx.is_global_admin:
            raise HTTPException(status_code=403, detail="cross-tenant federation access denied")
        return message.as_dict()

    @app.post("/federation/messages/{message_id}/receipt", tags=["federation"])
    def federation_message_receipt(message_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.message"])
        message = federation.get_message(message_id)
        if message.source_tenant_id != ctx.tenant_id and message.destination_tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=403, detail="cross-tenant federation access denied")
        return federation.add_receipt(message_id, ctx.tenant_id, payload.get("status", "accepted"), payload.get("reason", "")).as_dict()

    @app.post("/federation/delegations", tags=["federation"])
    def federation_delegation_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.delegate"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        agreement = federation.registry.get_agreement(payload["trust_agreement_id"])
        _assert_governance_tenant(ctx, agreement.as_dict())
        delegation = RemoteDelegation(
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
            trust_agreement_id=agreement.agreement_id,
            remote_org_id=agreement.remote_org_id,
            source_agent_id=payload["source_agent_id"],
            destination_agent_id=payload["destination_agent_id"],
            task_type=payload["task_type"],
            payload=dict(payload.get("payload", {})),
            created_by=ctx.principal_id,
        )
        try:
            requested = federation.request_delegation(
                delegation,
                signing_secret=payload.get("signing_secret", "local-federation-secret"),
                governance_approved=bool(payload.get("governance_approved", False)),
            )
        except (AuthorizationError, ValidationError) as exc:
            raise HTTPException(status_code=403 if isinstance(exc, AuthorizationError) else 400, detail=str(exc))
        metering.record(ctx.tenant_id, "federation_delegations", metadata={"delegation_id": requested.delegation_id})
        return requested.as_dict()

    @app.get("/federation/delegations/{delegation_id}", tags=["federation"])
    def federation_delegation_get(delegation_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.read"])
        delegation = federation.get_delegation(delegation_id)
        _assert_governance_tenant(ctx, delegation.as_dict())
        return delegation.as_dict()

    @app.post("/federation/delegations/{delegation_id}/complete", tags=["federation"])
    def federation_delegation_complete(delegation_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.delegate"])
        delegation = federation.get_delegation(delegation_id)
        _assert_governance_tenant(ctx, delegation.as_dict())
        return federation.complete_delegation(delegation_id, dict(payload.get("result", {}))).as_dict()

    @app.post("/federation/delegations/{delegation_id}/reject", tags=["federation"])
    def federation_delegation_reject(delegation_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.delegate"])
        delegation = federation.get_delegation(delegation_id)
        _assert_governance_tenant(ctx, delegation.as_dict())
        return federation.reject_delegation(delegation_id, payload.get("reason", "rejected")).as_dict()

    @app.get("/federation/reputation/{remote_org_id}", tags=["federation"])
    def federation_reputation(remote_org_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.read"])
        return federation.reputation(ctx.tenant_id, remote_org_id)

    @app.post("/billing/events", tags=["billing"])
    def record_billing_event(payload: BillingEventRequest, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["billing.write"], tenant_id=payload.tenant_id)
        service = BillingService(db, payment_processor=payment_processor)
        processed = service.record_event(
            tenant_id=payload.tenant_id,
            actor_id=payload.actor_id,
            event_type=payload.event_type,
            package_fqid=payload.package_fqid,
            idempotency_key=payload.idempotency_key,
        )
        return {"processed": processed}

    @app.get("/billing/invoice", response_model=InvoiceResponse, tags=["billing"])
    def get_invoice(tenant_id: str, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["billing.read"], tenant_id=tenant_id)
        service = BillingService(db, payment_processor=payment_processor)
        return InvoiceResponse(**service.build_invoice(tenant_id))

    @app.post("/billing/settle", tags=["billing"])
    def settle_invoice(tenant_id: str, currency: str, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["billing.write"], tenant_id=tenant_id)
        service = BillingService(db, payment_processor=payment_processor)
        result = service.settle_invoice(tenant_id, currency=currency, idempotency_key=f"settle:{tenant_id}:{currency}")
        return result

    @app.get("/billing/payments/{provider_txn_id}", tags=["billing"])
    def payment_status(provider_txn_id: str, request: Request, db: Session = Depends(get_db)):
        service = BillingService(db, payment_processor=payment_processor)
        payment = service.get_payment(provider_txn_id)
        require_scopes(request, ["billing.read"], tenant_id=payment["tenant_id"])
        return payment

    @app.post("/billing/webhooks/stripe", tags=["billing"])
    async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
        payload = await request.body()
        signature = request.headers.get("Stripe-Signature")
        event = parse_stripe_webhook_event(
            payload=payload,
            signature=signature,
            webhook_secret=settings.stripe_webhook_secret,
        )
        service = BillingService(db, payment_processor=payment_processor)
        return service.handle_stripe_webhook(event)

    @app.post("/queue/enqueue", response_model=QueueMessageResponse, tags=["queue"])
    def enqueue_job(payload: QueueEnqueueRequest, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["queue.write"])
        service = QueueService(db, backend=queue_backend)
        item = service.enqueue(payload.queue_name, payload.payload)
        return QueueMessageResponse(
            message_id=item.message_id,
            queue_name=item.queue_name,
            status="queued",
            payload=item.payload,
            attempts=item.attempts,
            created_at=item.created_at,
        )

    @app.post("/queue/dequeue", response_model=QueueMessageResponse | None, tags=["queue"])
    def dequeue_job(queue_name: str, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["queue.read"])
        service = QueueService(db, backend=queue_backend)
        item = service.dequeue(queue_name)
        if item is None:
            return None
        service.ack_success(item.message_id)
        visible_payload = {k: v for k, v in item.payload.items() if not k.startswith("__af_")}
        return QueueMessageResponse(
            message_id=item.message_id,
            queue_name=item.queue_name,
            status="done",
            payload=visible_payload,
            attempts=item.attempts,
            created_at=item.created_at,
        )

    @app.post("/mesh/send", tags=["mesh"])
    def mesh_send(payload: dict, request: Request):
        principal = require_scopes(request, ["mesh.send"])
        ctx = _tenant_context(request)
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "mesh_messages_per_minute")
        message = MeshMessage(
            source_agent=payload["source_agent"],
            destination_agent=payload["destination_agent"],
            payload={**payload.get("payload", {}), "tenant_id": ctx.tenant_id},
            message_type=payload.get("message_type", MessageType.REQUEST.value),
            correlation_id=payload.get("correlation_id") or f"corr-{uuid4().hex[:12]}",
            task_id=payload.get("task_id") or f"task-{uuid4().hex[:12]}",
        )
        sent = message_bus.send(message)
        event_store.append(
            EventType.MESSAGE.value,
            sent.correlation_id,
            {"principal_id": principal.principal_id, "tenant_id": ctx.tenant_id, "message": sent.as_dict()},
        )
        durable_store.put("mesh_messages", sent.correlation_id, {"tenant_id": ctx.tenant_id, **sent.as_dict()})
        metering.record(ctx.tenant_id, "message_sends", metadata={"correlation_id": sent.correlation_id})
        return sent.as_dict()

    @app.post("/mesh/broadcast", tags=["mesh"])
    def mesh_broadcast(payload: dict, request: Request):
        principal = require_scopes(request, ["mesh.broadcast"])
        ctx = _tenant_context(request)
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "mesh_messages_per_minute")
        messages = message_bus.broadcast(
            MeshMessage(
                source_agent=payload["source_agent"],
                destination_agent=None,
                payload={**payload.get("payload", {}), "tenant_id": ctx.tenant_id},
                message_type=MessageType.BROADCAST.value,
                correlation_id=payload.get("correlation_id") or f"corr-{uuid4().hex[:12]}",
                task_id=payload.get("task_id") or f"task-{uuid4().hex[:12]}",
            )
        )
        event_store.append(
            EventType.MESSAGE.value,
            payload.get("correlation_id", "broadcast"),
            {"principal_id": principal.principal_id, "tenant_id": ctx.tenant_id, "count": len(messages)},
        )
        metering.record(ctx.tenant_id, "message_sends", quantity=len(messages), metadata={"broadcast": True})
        return {"items": [message.as_dict() for message in messages], "count": len(messages)}

    @app.post("/workflow/start", tags=["workflow"])
    def workflow_start(payload: dict, request: Request):
        principal = require_scopes(request, ["workflow.start"])
        ctx = _tenant_context(request)
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "workflow_runs_per_day")
        existing = _workflow_owner(payload["workflow_id"])
        if existing is not None:
            isolation.assert_tenant(ctx, existing)

        def api_node_runner(node: TaskNode, node_payload: dict[str, object]) -> dict[str, object]:
            return {
                "agent_id": node.agent_id,
                "node_id": node.node_id,
                "capability": node.capability,
                "input": node_payload["initial_payload"],
                "dependency_results": node_payload["dependency_results"],
            }

        initial_payload = {
            **payload.get("initial_payload", {}),
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": principal.principal_id,
        }
        durable_store.put(
            "workflows",
            payload["workflow_id"],
            {
                "workflow_id": payload["workflow_id"],
                "tenant_id": ctx.tenant_id,
                "organization_id": ctx.organization_id,
                "created_by": principal.principal_id,
            },
        )
        result = coordinator.start_workflow(
            workflow_id=payload["workflow_id"],
            nodes=payload["nodes"],
            initial_payload=initial_payload,
            approved_nodes=set(payload.get("approved_nodes", [])),
            node_runner=api_node_runner,
        )
        metering.record(ctx.tenant_id, "workflow_runs", metadata={"workflow_id": payload["workflow_id"]})
        return result

    @app.get("/workflow/{workflow_id}", tags=["workflow"])
    def workflow_get(workflow_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["workflow.read"])
        _assert_workflow_tenant(ctx, workflow_id)
        workflow = workflow_engine.get(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        return workflow

    @app.get("/events", tags=["events"])
    def events_list(request: Request, aggregate_id: str | None = None):
        ctx = _tenant_context(request)
        require_scopes(request, ["events.read"])
        events = [
            event for event in event_store.replay(aggregate_id)
            if event.payload.get("tenant_id") == ctx.tenant_id
        ]
        return {"items": [event.as_dict() for event in events], "total": len(events)}

    @app.get("/events/{event_id}", tags=["events"])
    def events_get(event_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["events.read"])
        event = event_store.get(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        if event.payload.get("tenant_id") != ctx.tenant_id:
            raise HTTPException(status_code=403, detail="cross-tenant access denied")
        return event.as_dict()

    @app.get("/workflow/{workflow_id}/events", tags=["workflow"])
    def workflow_events(workflow_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["events.read", "workflow.read"])
        _assert_workflow_tenant(ctx, workflow_id)
        events = [event for event in event_store.replay(workflow_id) if event.payload.get("tenant_id") == ctx.tenant_id]
        return {"items": [event.as_dict() for event in events], "total": len(events)}

    @app.post("/workflow/{workflow_id}/recover", tags=["workflow"])
    def workflow_recover(workflow_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["workflow.recover"])
        _assert_workflow_tenant(ctx, workflow_id)
        metering.record(ctx.tenant_id, "recovery_operations", metadata={"workflow_id": workflow_id})
        try:
            return ReplayRecoveryEngine(event_store=event_store, persistence=durable_store).recover_workflow(workflow_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="workflow not found")
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    @app.get("/memory/{agent_id}", tags=["memory"])
    def memory_list(agent_id: str, request: Request):
        principal = require_scopes(request, ["memory.read"])
        _tenant_context(request)
        records = memory_store.list_for_agent(tenant_id=principal.tenant_id, owner_agent_id=agent_id)
        return {"items": [record.as_dict() for record in records], "total": len(records)}

    @app.post("/memory/{agent_id}", tags=["memory"])
    def memory_create(agent_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["memory.write"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "memory_records")
        try:
            record = memory_store.create(
                owner_agent_id=agent_id,
                tenant_id=ctx.tenant_id,
                source_workflow_id=payload.get("source_workflow_id"),
                classification=payload.get("classification", "internal"),
                content=payload.get("content", {}),
                veil_token_refs=tuple(payload.get("veil_token_refs", ())),
                memory_type=payload.get("memory_type", "short_term"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        event_store.append(
            "memory.recorded",
            agent_id,
            {"memory_id": record.memory_id, "tenant_id": ctx.tenant_id, "organization_id": ctx.organization_id},
        )
        metering.record(ctx.tenant_id, "memory_writes", metadata={"memory_id": record.memory_id})
        return record.as_dict()

    @app.delete("/memory/{agent_id}/{memory_id}", tags=["memory"])
    def memory_delete(agent_id: str, memory_id: str, request: Request):
        ctx = _tenant_context(request)
        principal = require_scopes(request, ["memory.delete"])
        try:
            deleted = memory_store.delete(
                tenant_id=principal.tenant_id,
                owner_agent_id=agent_id,
                memory_id=memory_id,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        if not deleted:
            raise HTTPException(status_code=404, detail="memory not found")
        event_store.append(
            "memory.deleted",
            agent_id,
            {"memory_id": memory_id, "tenant_id": ctx.tenant_id, "organization_id": ctx.organization_id},
        )
        return {"deleted": True, "memory_id": memory_id}

    @app.get("/agents", tags=["agents"])
    def agents_list(request: Request, capability: str | None = None, version: str | None = None, healthy_only: bool = True):
        _tenant_context(request)
        require_scopes(request, ["agents.read"])
        if capability:
            items = mesh_discovery.discover(capability=capability, version=version, healthy_only=healthy_only)
        else:
            items = [entry.as_dict() for entry in mesh_directory.list_agents()]
        return {"items": items, "total": len(items)}

    @app.get("/agents/{agent_id}", tags=["agents"])
    def agents_get(agent_id: str, request: Request):
        _tenant_context(request)
        require_scopes(request, ["agents.read"])
        entry = mesh_directory.get(agent_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="agent not found")
        return entry.as_dict()

    @app.get("/agents/{agent_id}/reputation", tags=["agents"])
    def agents_reputation(agent_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["reputation.read"])
        if mesh_directory.get(agent_id) is None:
            raise HTTPException(status_code=404, detail="agent not found")
        return reputation.get(agent_id, tenant_id=ctx.tenant_id).as_dict()

    @app.get("/agents/{agent_id}/quality", tags=["agents"])
    def agents_quality(agent_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["evaluations.read"])
        return _latest_quality(ctx, "agent_output", agent_id)

    @app.post("/connectors/register", tags=["enterprise-connectors"])
    def enterprise_connector_register(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["connectors:write"])
        try:
            manifest = EnterpriseConnectorManifest.from_dict(payload)
            return enterprise_connectors.registry.register(
                manifest,
                tenant_id=ctx.tenant_id,
                created_by=ctx.principal_id,
            ).as_dict()
        except (ValueError, ConflictError) as exc:
            raise HTTPException(status_code=409 if isinstance(exc, ConflictError) else 400, detail=str(exc))

    @app.post("/connectors/{connector_id}/enable", tags=["enterprise-connectors"])
    def enterprise_connector_enable(connector_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["connectors:admin"])
        try:
            credential = enterprise_connectors.vault.get(ctx.tenant_id, str(payload["credential_id"]))
            policy = EnterpriseConnectorPolicy(
                policy_id=str(payload.get("policy_id", f"policy-{connector_id}")),
                tenant_id=ctx.tenant_id,
                allowed_agents=tuple(str(item) for item in payload.get("allowed_agents", ())),
                allowed_connectors=tuple(str(item) for item in payload.get("allowed_connectors", (connector_id,))),
                allowed_actions=tuple(str(item) for item in payload.get("allowed_actions", ())),
                allowed_credential_types=tuple(str(item) for item in payload.get("allowed_credential_types", (credential.credential_type,))),
                maximum_risk=str(payload.get("maximum_risk", "medium")),
                minimum_package_trust_score=float(payload.get("minimum_package_trust_score", 0.8)),
                require_veil=bool(payload.get("require_veil", True)),
            )
            return enterprise_connectors.registry.enable(
                ctx,
                connector_id,
                version=payload.get("version"),
                credential_ref=credential.reference_id,
                policy=policy,
            ).as_dict()
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"missing field: {exc}")
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (AuthorizationError, ValueError) as exc:
            raise HTTPException(status_code=403 if isinstance(exc, AuthorizationError) else 400, detail=str(exc))

    @app.post("/connectors/{connector_id}/disable", tags=["enterprise-connectors"])
    def enterprise_connector_disable(connector_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["connectors:admin"])
        try:
            return enterprise_connectors.registry.disable(ctx, connector_id).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/connectors/{connector_id}/execute", tags=["enterprise-connectors"])
    def enterprise_connector_execute(connector_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        principal = require_scopes(request, ["connectors:execute"])
        try:
            result = enterprise_connectors.execution.execute(
                ctx=ctx,
                connector_id=connector_id,
                agent_id=str(payload["agent_id"]),
                action=str(payload["action"]),
                payload=dict(payload.get("payload", {})),
                agent_permissions=set(principal.scopes),
                package_trust_score=float(payload.get("package_trust_score", 1.0)),
            )
            metering.record(ctx.tenant_id, "connector_executions", metadata={"execution_id": result.execution_id})
            return result.as_dict()
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"missing field: {exc}")
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/credentials", tags=["enterprise-connectors"])
    def connector_credential_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["credentials:write"])
        try:
            return enterprise_connectors.create_credential(ctx, payload).as_dict()
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/credentials/{credential_id}/rotate", tags=["enterprise-connectors"])
    def connector_credential_rotate(credential_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["credentials:rotate"])
        try:
            return enterprise_connectors.rotate_credential(ctx, credential_id, str(payload["secret"])).as_dict()
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except (NotFoundError, AuthorizationError) as exc:
            raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 403, detail=str(exc))

    @app.post("/credentials/{credential_id}/revoke", tags=["enterprise-connectors"])
    def connector_credential_revoke(credential_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["credentials:rotate"])
        try:
            return enterprise_connectors.revoke_credential(ctx, credential_id).as_dict()
        except (NotFoundError, AuthorizationError) as exc:
            raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 403, detail=str(exc))

    @app.post("/observability/metrics", tags=["agent-observability"])
    def observability_metric_record(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["observability:write"])
        try:
            recorded = operational_intelligence.record_metric(
                AgentMetric(
                    tenant_id=ctx.tenant_id,
                    agent_id=payload["agent_id"],
                    version=payload.get("version", "unknown"),
                    metric=payload["metric"],
                    value=float(payload["value"]),
                    metadata=dict(payload.get("metadata", {})),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "agent_observability_metrics", metadata={"metric_id": recorded.metric_id})
        return recorded.as_dict()

    @app.get("/observability/metrics", tags=["agent-observability"])
    def observability_metrics_list(
        request: Request,
        agent_id: str | None = None,
        version: str | None = None,
        metric: str | None = None,
    ):
        ctx = _tenant_context(request)
        require_scopes(request, ["observability:read"])
        items = operational_intelligence.list_metrics(ctx, agent_id=agent_id, version=version, metric=metric)
        return {
            "items": [item.as_dict() for item in items],
            "total": len(items),
            "aggregation": operational_intelligence.aggregate(ctx, agent_id=agent_id, version=version),
        }

    @app.get("/agents/{agent_id}/health", tags=["agent-observability"])
    def agent_health(agent_id: str, request: Request, version: str | None = None):
        ctx = _tenant_context(request)
        require_scopes(request, ["health:read"])
        try:
            return operational_intelligence.latest_health(ctx, agent_id, version=version).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/agents/{agent_id}/health/history", tags=["agent-observability"])
    def agent_health_history(agent_id: str, request: Request, version: str | None = None):
        ctx = _tenant_context(request)
        require_scopes(request, ["health:read"])
        items = operational_intelligence.health_history(ctx, agent_id, version=version)
        return {"items": [item.as_dict() for item in items], "total": len(items)}

    @app.get("/agents/{agent_id}/drift", tags=["agent-observability"])
    def agent_drift(agent_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["drift:read"])
        items = operational_intelligence.list_drift(ctx, agent_id)
        return {"items": [item.as_dict() for item in items], "total": len(items)}

    @app.get("/agents/{agent_id}/anomalies", tags=["agent-observability"])
    def agent_anomalies(agent_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["anomaly:read"])
        items = operational_intelligence.list_anomalies(ctx, agent_id)
        return {"items": [item.as_dict() for item in items], "total": len(items)}

    @app.get("/agents/{agent_id}/recommendations", tags=["agent-observability"])
    def agent_recommendations(agent_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["recommendations:read"])
        items = operational_intelligence.list_recommendations(ctx, agent_id)
        return {"items": [item.as_dict() for item in items], "total": len(items)}

    @app.post("/agents/{agent_id}/recommendations/{recommendation_id}/approve", tags=["agent-observability"])
    def agent_recommendation_approve(agent_id: str, recommendation_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["recommendations:approve"])
        try:
            return operational_intelligence.approve_recommendation(ctx, agent_id, recommendation_id).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/agents/{agent_id}/compare", tags=["agent-observability"])
    def agent_version_compare(agent_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["observability:read"])
        try:
            return operational_intelligence.compare_versions(
                ctx,
                agent_id,
                str(payload["baseline_version"]),
                str(payload["candidate_version"]),
            ).as_dict()
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/connectors", tags=["connectors"])
    def connector_register(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["connectors.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        try:
            connector = connector_registry.register(
                ctx=ctx,
                manifest=_connector_manifest_from_payload(payload),
                credentials=_connector_credentials_from_payload(payload),
                policy=_connector_policy_from_payload(payload),
                connector_id=payload.get("connector_id"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "connector_registered", metadata={"connector_id": connector.connector_id})
        return connector.as_dict()

    @app.get("/connectors", tags=["connectors"])
    def connectors_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["connectors.read"])
        legacy = [item.as_dict() for item in connector_registry.list(ctx)]
        enterprise = enterprise_connectors.registry.list(ctx)
        items = [*enterprise, *legacy]
        return {"items": items, "total": len(items)}

    @app.get("/connectors/{connector_id}", tags=["connectors"])
    def connector_get(connector_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["connectors.read"])
        try:
            return enterprise_connectors.registry.get(ctx, connector_id).as_dict()
        except NotFoundError:
            try:
                return connector_registry.get(ctx, connector_id).as_dict()
            except NotFoundError:
                raise HTTPException(status_code=404, detail="connector not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/connectors/{connector_id}/sync", tags=["connectors"])
    def connector_sync(connector_id: str, payload: dict, request: Request):
        return _connector_operation(connector_id, "sync", payload, request, create_job=True)

    @app.post("/connectors/{connector_id}/search", tags=["connectors"])
    def connector_search(connector_id: str, payload: dict, request: Request):
        return _connector_operation(connector_id, "search", payload, request, create_job=True)

    @app.post("/connectors/{connector_id}/fetch", tags=["connectors"])
    def connector_fetch(connector_id: str, payload: dict, request: Request):
        return _connector_operation(connector_id, "fetch", payload, request, create_job=True)

    @app.post("/connectors/{connector_id}/webhook", tags=["connectors"])
    def connector_webhook(connector_id: str, payload: dict, request: Request):
        return _connector_operation(connector_id, "webhook", payload, request, create_job=True)

    @app.get("/connectors/{connector_id}/health", tags=["connectors"])
    def connector_health(connector_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["connectors.read"])
        try:
            return connector_registry.health(ctx=ctx, connector_id=connector_id)
        except NotFoundError:
            raise HTTPException(status_code=404, detail="connector not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    def _connector_operation(connector_id: str, operation: str, payload: dict, request: Request, *, create_job: bool = False):
        ctx = _tenant_context(request)
        require_scopes(request, ["connectors.manage" if operation in {"sync", "webhook"} else "connectors.read"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        try:
            result = connector_registry.execute(ctx=ctx, connector_id=connector_id, operation=operation, payload=dict(payload))
            if create_job:
                job = connector_registry.create_job(ctx=ctx, connector_id=connector_id, operation=operation, payload=dict(payload))
                return {"result": result.as_dict(), "job": job.as_dict()}
            return result.as_dict()
        except NotFoundError:
            raise HTTPException(status_code=404, detail="connector not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/tools", tags=["tools"])
    def tool_register(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["tools.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        try:
            tool = tool_registry.register(
                ctx=ctx,
                manifest=_tool_manifest_from_payload(payload),
                permission=_tool_permission_from_payload(payload),
                tool_id=payload.get("tool_id"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "tool_registered", metadata={"tool_id": tool.tool_id})
        return tool.as_dict()

    @app.get("/tools", tags=["tools"])
    def tools_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["tools.read"])
        tools = tool_registry.list(ctx)
        return {"items": [tool.as_dict() for tool in tools], "total": len(tools)}

    @app.get("/tools/{tool_id}", tags=["tools"])
    def tool_get(tool_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["tools.read"])
        try:
            return tool_registry.get(ctx, tool_id).as_dict()
        except NotFoundError:
            raise HTTPException(status_code=404, detail="tool not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/tools/{tool_id}/execute", tags=["tools"])
    def tool_execute(tool_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["tools.execute"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        try:
            result, job = tool_registry.execute(
                ctx=ctx,
                tool_id=tool_id,
                payload=dict(payload.get("payload", payload)),
                governance_approved=bool(payload.get("governance_approved", False)),
            )
        except NotFoundError:
            raise HTTPException(status_code=404, detail="tool not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "tool_executions", metadata={"tool_id": tool_id, "execution_id": result.execution_id})
        return {"result": result.as_dict(), "job": job.as_dict() if job else None}

    @app.get("/tools/{tool_id}/health", tags=["tools"])
    def tool_health(tool_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["tools.read"])
        try:
            return tool_registry.health(ctx=ctx, tool_id=tool_id)
        except NotFoundError:
            raise HTTPException(status_code=404, detail="tool not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.get("/tools/executions/{execution_id}", tags=["tools"])
    def tool_execution_get(execution_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["tools.read"])
        try:
            return tool_registry.get_execution(ctx, execution_id).as_dict()
        except NotFoundError:
            raise HTTPException(status_code=404, detail="tool execution not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/evaluations/datasets", tags=["evaluations"])
    def evaluation_dataset_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["evaluations.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        try:
            dataset = evaluation_runner.create_dataset(
                EvaluationDataset(
                    tenant_id=ctx.tenant_id,
                    organization_id=ctx.organization_id,
                    name=payload["name"],
                    cases=tuple(EvaluationCase.from_dict(item) for item in payload.get("cases", ())),
                    created_by=ctx.principal_id,
                    dataset_id=payload.get("dataset_id", None) or f"eval-dataset-{uuid4().hex[:12]}",
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "evaluation_datasets", metadata={"dataset_id": dataset.dataset_id})
        return dataset.as_dict()

    @app.get("/evaluations/datasets", tags=["evaluations"])
    def evaluation_datasets_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["evaluations.read"])
        items = evaluation_runner.list_datasets(ctx)
        return {"items": [item.as_dict() for item in items], "total": len(items)}

    @app.post("/evaluations/run", tags=["evaluations"])
    def evaluation_run(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["evaluations.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        try:
            result = evaluation_runner.run(
                ctx=ctx,
                dataset_id=payload["dataset_id"],
                target_type=payload["target_type"],
                target_id=payload["target_id"],
                outputs=[dict(item) for item in payload.get("outputs", ())],
            )
        except NotFoundError:
            raise HTTPException(status_code=404, detail="evaluation dataset not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        metering.record(ctx.tenant_id, "evaluation_runs", metadata={"run_id": result.run_id})
        if result.target_type == "agent_output":
            operational_intelligence.record_metric(
                AgentMetric(
                    tenant_id=ctx.tenant_id,
                    agent_id=result.target_id,
                    version=str(payload.get("version", "unknown")),
                    metric="evaluation_score",
                    value=result.overall_score,
                    metadata={"run_id": result.run_id},
                )
            )
        return result.as_dict()

    @app.get("/evaluations/runs/{run_id}/scorecard", tags=["evaluations"])
    def evaluation_scorecard(run_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["evaluations.read"])
        try:
            return evaluation_runner.scorecard(ctx, run_id).as_dict()
        except NotFoundError:
            raise HTTPException(status_code=404, detail="evaluation run not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.get("/evaluations/runs/{run_id}", tags=["evaluations"])
    def evaluation_run_get(run_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["evaluations.read"])
        try:
            return evaluation_runner.get_result(ctx, run_id).as_dict()
        except NotFoundError:
            raise HTTPException(status_code=404, detail="evaluation run not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/feedback", tags=["feedback"])
    def feedback_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["feedback.write"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        record = feedback_service.create(ctx, payload)
        metering.record(ctx.tenant_id, "feedback_records", metadata={"feedback_id": record.feedback_id})
        if payload.get("target_type") == "agent" and payload.get("target_id"):
            if payload.get("rating") is not None:
                operational_intelligence.record_metric(
                    AgentMetric(
                        tenant_id=ctx.tenant_id,
                        agent_id=str(payload["target_id"]),
                        version=str(payload.get("version", "unknown")),
                        metric="user_rating",
                        value=float(payload["rating"]),
                        metadata={"feedback_id": record.feedback_id},
                    )
                )
            if payload.get("correction_notes"):
                operational_intelligence.record_metric(
                    AgentMetric(
                        tenant_id=ctx.tenant_id,
                        agent_id=str(payload["target_id"]),
                        version=str(payload.get("version", "unknown")),
                        metric="correction_frequency",
                        value=1.0,
                        metadata={"feedback_id": record.feedback_id},
                    )
                )
        return record.as_dict()

    @app.get("/feedback", tags=["feedback"])
    def feedback_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["feedback.read"])
        items = feedback_service.list(ctx)
        return {"items": [item.as_dict() for item in items], "total": len(items)}

    @app.post("/runtime/jobs", tags=["runtime"])
    def runtime_job_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        job = RuntimeJob(
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
            created_by=ctx.principal_id,
            job_type=payload["job_type"],
            payload=dict(payload.get("payload", {})),
            queue_name=payload.get("queue_name", "default"),
            max_attempts=int(payload.get("max_attempts", settings.queue_max_attempts)),
        )
        try:
            created = cloud_runtime.submit(job)
            if payload.get("dispatch_now"):
                dispatched = cloud_runtime.dispatcher.dispatch_one(
                    tenant_id=ctx.tenant_id,
                    queue_name=created.queue_name,
                    worker_id=str(payload.get("worker_id", "api-dispatcher")),
                )
                return (dispatched or created).as_dict()
        except (ValueError, AuthorizationError, ConflictError) as exc:
            raise HTTPException(status_code=400 if isinstance(exc, ValueError) else 403 if isinstance(exc, AuthorizationError) else 409, detail=str(exc))
        metering.record(ctx.tenant_id, "runtime_jobs", metadata={"job_id": created.job_id})
        category = {
            "agent_run": "agent_run",
            "workflow_step": "workflow_run",
            "tool_execution": "tool_execution",
            "connector_sync": "connector_sync",
            "evaluation_run": "evaluation_run",
            "audit_export": "audit_bundle_export",
        }.get(created.job_type, "queue_worker_runtime")
        cost = cost_tracker.record(ctx.tenant_id, category, source_id=created.job_id, metadata={"job_type": created.job_type})
        event_store.append("economics.cost.recorded", cost.event_id, cost.as_dict())
        return created.as_dict()

    @app.get("/runtime/jobs", tags=["runtime"])
    def runtime_jobs_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.read"])
        jobs = cloud_runtime.list_jobs(None if ctx.is_global_admin else ctx.tenant_id)
        return {"items": [job.as_dict() for job in jobs], "total": len(jobs)}

    @app.get("/runtime/jobs/{job_id}", tags=["runtime"])
    def runtime_job_get(job_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.read"])
        job = cloud_runtime.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        _assert_governance_tenant(ctx, job.as_dict())
        return job.as_dict()

    @app.post("/runtime/jobs/{job_id}/cancel", tags=["runtime"])
    def runtime_job_cancel(job_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.manage"])
        job = cloud_runtime.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        _assert_governance_tenant(ctx, job.as_dict())
        return cloud_runtime.cancel(job_id).as_dict()

    @app.post("/runtime/jobs/{job_id}/retry", tags=["runtime"])
    def runtime_job_retry(job_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        job = cloud_runtime.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        _assert_governance_tenant(ctx, job.as_dict())
        return cloud_runtime.retry(job_id).as_dict()

    @app.get("/runtime/dead-letter", tags=["runtime"])
    def runtime_dead_letter(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.read"])
        jobs = cloud_queue.dead_letters(tenant_id=None if ctx.is_global_admin else ctx.tenant_id)
        return {"items": [job.as_dict() for job in jobs], "total": len(jobs)}

    @app.post("/runtime/dead-letter/{job_id}/requeue", tags=["runtime"])
    def runtime_dead_letter_requeue(job_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        job = cloud_runtime.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        _assert_governance_tenant(ctx, job.as_dict())
        return cloud_runtime.requeue_dead_letter(job_id).as_dict()

    @app.post("/runtime/workers/register", tags=["runtime"])
    def runtime_worker_register(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.workers.manage"])
        worker = Worker(
            worker_id=payload.get("worker_id") or f"worker-{uuid4().hex[:12]}",
            tenant_id=ctx.tenant_id,
            queue_names=tuple(payload.get("queue_names", ("default",))),
            capabilities=tuple(payload.get("capabilities", ())),
        )
        return cloud_runtime.register_worker(worker).as_dict()

    @app.post("/runtime/workers/{worker_id}/heartbeat", tags=["runtime"])
    def runtime_worker_heartbeat(worker_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.workers.manage"])
        worker = cloud_runtime.workers.get(worker_id)
        if worker is None:
            raise HTTPException(status_code=404, detail="worker not found")
        _assert_governance_tenant(ctx, worker.as_dict())
        return cloud_runtime.heartbeat(worker_id).as_dict()

    @app.get("/runtime/workers", tags=["runtime"])
    def runtime_workers_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.read"])
        workers = cloud_runtime.workers.list(None if ctx.is_global_admin else ctx.tenant_id)
        return {"items": [worker.as_dict() for worker in workers], "total": len(workers)}

    @app.post("/runtime/schedules", tags=["runtime"])
    def runtime_schedule_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.schedules.manage"])
        run_at = datetime.fromisoformat(payload["run_at"]) if payload.get("run_at") else None
        schedule = scheduler.create(
            ScheduledJob(
                tenant_id=ctx.tenant_id,
                organization_id=ctx.organization_id,
                created_by=ctx.principal_id,
                job_type=payload["job_type"],
                payload=dict(payload.get("payload", {})),
                schedule_type=payload.get("schedule_type", "one_time"),
                cron=payload.get("cron"),
                run_at=run_at,
            )
        )
        return schedule.as_dict()

    @app.get("/runtime/schedules", tags=["runtime"])
    def runtime_schedules_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.read"])
        schedules = scheduler.list(ctx.tenant_id)
        return {"items": [schedule.as_dict() for schedule in schedules], "total": len(schedules)}

    @app.post("/runtime/schedules/{schedule_id}/disable", tags=["runtime"])
    def runtime_schedule_disable(schedule_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.schedules.manage"])
        schedule = scheduler.get(schedule_id)
        if schedule is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        _assert_governance_tenant(ctx, schedule.as_dict())
        return scheduler.set_enabled(schedule_id, False).as_dict()

    @app.post("/runtime/schedules/{schedule_id}/enable", tags=["runtime"])
    def runtime_schedule_enable(schedule_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.schedules.manage"])
        schedule = scheduler.get(schedule_id)
        if schedule is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        _assert_governance_tenant(ctx, schedule.as_dict())
        return scheduler.set_enabled(schedule_id, True).as_dict()

    @app.get("/metrics", tags=["system"])
    @app.get("/metrics/prometheus", tags=["system"])
    def metrics(request: Request):
        if not settings.metrics_public:
            require_scopes(request, ["metrics.read"])
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/metrics/tenants/{tenant_id}", tags=["system"])
    def tenant_metrics(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["usage.read"])
        runtime_metrics = TenantUsageMetrics(cloud_runtime).snapshot(tenant_id)
        runtime_metrics["runtime"] = metrics_registry.runtime_snapshot(cloud_runtime)
        runtime_metrics["usage"] = metering.aggregate(tenant_id)
        return runtime_metrics

    @app.get("/runtime/agents", tags=["runtime"])
    def runtime_agents(request: Request):
        require_scopes(request, ["runtime.read"])
        return {"items": control_plane.runtime_agents()}

    @app.post("/runtime/install", tags=["runtime"])
    def runtime_install(payload: dict, request: Request):
        require_scopes(request, ["runtime.install"])
        agent_id = control_plane.install_runtime_agent(
            manifest=payload["manifest"],
            payload=payload["payload"].encode("utf-8"),
            signer_id=payload["signer_id"],
            signer_key=payload["signer_key"],
            signature=payload["signature"],
        )
        return {"agent_id": agent_id}

    @app.post("/runtime/load", tags=["runtime"])
    def runtime_load(payload: dict, request: Request):
        require_scopes(request, ["runtime.run"])
        control_plane.runtime_load(payload["agent_id"])
        return {"status": "loaded"}

    @app.post("/runtime/run", tags=["runtime"])
    def runtime_run(payload: dict, request: Request):
        require_scopes(request, ["runtime.run"])
        return control_plane.runtime_run(
            agent_id=payload["agent_id"],
            request=payload["request"],
            user_id=payload["user_id"],
            session_id=payload["session_id"],
        )

    @app.post("/runtime/suspend", tags=["runtime"])
    def runtime_suspend(payload: dict, request: Request):
        require_scopes(request, ["runtime.run"])
        control_plane.runtime_suspend(payload["agent_id"])
        return {"status": "suspended"}

    @app.post("/runtime/uninstall", tags=["runtime"])
    def runtime_uninstall(payload: dict, request: Request):
        require_scopes(request, ["runtime.install"])
        control_plane.runtime_uninstall(payload["agent_id"])
        return {"status": "uninstalled"}

    @app.post("/enterprise/rbac/assign", tags=["enterprise"])
    def enterprise_rbac_assign(payload: dict, request: Request):
        require_scopes(request, ["enterprise.rbac.write"])
        control_plane.assign_role(payload["principal_id"], payload["role"])
        return {"status": "ok"}

    @app.post("/enterprise/rbac/check", tags=["enterprise"])
    def enterprise_rbac_check(payload: dict, request: Request):
        require_scopes(request, ["enterprise.rbac.read"])
        control_plane.check_permission(payload["principal_id"], payload["permission"])
        return {"allowed": True}

    @app.post("/enterprise/namespace/create", tags=["enterprise"])
    def enterprise_namespace_create(payload: dict, request: Request):
        require_scopes(request, ["enterprise.namespace.write"], tenant_id=payload["owner_tenant_id"])
        control_plane.create_namespace(payload["owner_tenant_id"], payload["namespace"])
        return {"status": "created"}

    @app.post("/enterprise/namespace/grant", tags=["enterprise"])
    def enterprise_namespace_grant(payload: dict, request: Request):
        require_scopes(request, ["enterprise.namespace.write"], tenant_id=payload["owner_tenant_id"])
        control_plane.grant_namespace_access(
            payload["owner_tenant_id"],
            payload["namespace"],
            payload["target_tenant_id"],
        )
        return {"status": "granted"}

    @app.post("/enterprise/namespace/check", tags=["enterprise"])
    def enterprise_namespace_check(payload: dict, request: Request):
        require_scopes(request, ["enterprise.namespace.read"], tenant_id=payload["tenant_id"])
        control_plane.check_namespace_access(payload["tenant_id"], payload["namespace"])
        return {"allowed": True}

    @app.post("/enterprise/audit/append", tags=["enterprise"])
    def enterprise_audit_append(payload: dict, request: Request):
        require_scopes(request, ["enterprise.audit.write"])
        return control_plane.append_audit(
            actor_id=payload["actor_id"],
            action=payload["action"],
            target=payload["target"],
            metadata=payload.get("metadata", {}),
        )

    @app.post("/enterprise/audit/export", tags=["enterprise"])
    def enterprise_audit_export(payload: dict, request: Request):
        require_scopes(request, ["enterprise.audit.read"])
        path = control_plane.export_siem_audit(payload["output_file"])
        return {"path": path}

    @app.post("/reviews/submit", tags=["reviews"])
    def reviews_submit(payload: dict, request: Request):
        require_scopes(request, ["reviews.write"], tenant_id=payload["tenant_id"])
        review_id = control_plane.submit_review(
            Rating(
                tenant_id=payload["tenant_id"],
                package_fqid=payload["package_fqid"],
                user_id=payload["user_id"],
                stars=int(payload["stars"]),
                review=payload["review"],
            )
        )
        return {"review_id": review_id}

    @app.post("/reviews/moderation/pending", tags=["reviews"])
    def reviews_pending(request: Request):
        require_scopes(request, ["reviews.moderate"])
        return {"items": control_plane.pending_reviews()}

    @app.post("/reviews/moderation/resolve", tags=["reviews"])
    def reviews_resolve(payload: dict, request: Request):
        require_scopes(request, ["reviews.moderate"])
        control_plane.moderate_review(int(payload["review_id"]), approved=bool(payload["approved"]))
        return {"status": "ok"}

    @app.post("/compliance/gdpr/request", tags=["compliance"])
    def gdpr_request(payload: dict, request: Request):
        require_scopes(request, ["compliance.gdpr.write"], tenant_id=payload["tenant_id"])
        request_id = control_plane.request_gdpr_deletion(
            tenant_id=payload["tenant_id"],
            user_id=payload.get("user_id"),
            reason=payload["reason"],
        )
        return {"request_id": request_id}

    @app.post("/compliance/gdpr/process", tags=["compliance"])
    def gdpr_process(request: Request):
        require_scopes(request, ["compliance.gdpr.write"])
        return {"processed": control_plane.process_gdpr_deletions()}

    @app.post("/compliance/legal/publish", tags=["compliance"])
    def legal_publish(payload: dict, request: Request):
        require_scopes(request, ["compliance.legal.write"])
        control_plane.publish_legal_document(
            payload["doc_type"],
            payload["version"],
            payload["content"],
        )
        return {"status": "ok"}

    @app.post("/compliance/legal/accept", tags=["compliance"])
    def legal_accept(payload: dict, request: Request):
        require_scopes(request, ["compliance.legal.read"])
        return control_plane.accept_legal_document(payload["doc_type"], payload["principal_id"])

    @app.post("/ops/backup", tags=["ops"])
    def ops_backup(request: Request):
        require_scopes(request, ["ops.backup.write"])
        backup = control_plane.create_backup()
        return {"backup_file": backup}

    @app.get("/ops/backups", tags=["ops"])
    def ops_list_backups(request: Request):
        require_scopes(request, ["ops.backup.read"])
        items = control_plane.list_backups()
        return {"items": items}

    @app.post("/ops/restore", tags=["ops"])
    def ops_restore(payload: dict, request: Request):
        require_scopes(request, ["ops.backup.write"])
        backup_file = payload.get("backup_file")
        if not backup_file:
            raise HTTPException(status_code=400, detail="backup_file required")
        try:
            control_plane.restore_backup(backup_file)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"status": "restored", "backup_file": backup_file}

    @app.post("/audit/append", tags=["audit"])
    def append_audit(actor_id: str, action: str, target: str, metadata: dict | None, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["audit.write"])
        service = AuditService(db)
        return service.append(actor_id=actor_id, action=action, target=target, metadata=metadata)

    return app
