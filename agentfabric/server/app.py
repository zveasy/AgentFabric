"""FastAPI application with auth middleware and OpenAPI docs."""

from __future__ import annotations

from contextlib import asynccontextmanager
import shutil
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from agentfabric.errors import ConflictError, NotFoundError, ValidationError
from agentfabric.server.auth import AuthService, require_scopes
from agentfabric.server.config import Settings, get_settings
from agentfabric.server.database import Base, build_session_factory
from agentfabric.server.payments import MockPaymentProcessor, StripePaymentProcessor
from agentfabric.server.queue import InMemoryQueueBackend, RedisQueueBackend
from agentfabric.server.schemas import (
    AddMaintainerRequest,
    AgentProjectResponse,
    AssignRoleRequest,
    BillingEventRequest,
    ContributionResponse,
    CreateAgentProjectRequest,
    CreateBranchRequest,
    HealthResponse,
    InstallPackageRequest,
    InvoiceResponse,
    IssueTokenRequest,
    ListAgentProjectsResponse,
    ListContributionsResponse,
    ListPackagesResponse,
    PackageResponse,
    PublishPackageRequest,
    QueueEnqueueRequest,
    QueueMessageResponse,
    RegisterPrincipalRequest,
    ReviewContributionRequest,
    SubmitReviewRequest,
    ReviewSummaryResponse,
    RotateTokenRequest,
    SubmitContributionRequest,
    TokenResponse,
    WorkflowRunRequest,
)
from agentfabric.server.services import (
    AgentProjectService,
    AuditService,
    BillingService,
    PackageService,
    QueueService,
    ReviewService,
)
from agentfabric.server.signing import CosignVerifier, DigestFallbackVerifier
from agentfabric.server.forge_ui import render_forge_ui


def choose_queue_backend(settings: Settings):
    if settings.redis_url.startswith("redis://"):
        try:
            return RedisQueueBackend(settings.redis_url)
        except Exception:
            return InMemoryQueueBackend()
    return InMemoryQueueBackend()


def choose_signing_verifier():
    if shutil.which("cosign") is not None:
        return CosignVerifier()
    return DigestFallbackVerifier()


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()
    session_factory, engine = build_session_factory(settings)
    Base.metadata.create_all(bind=engine)
    auth = AuthService(settings)
    queue_backend = choose_queue_backend(settings)
    signing_verifier = choose_signing_verifier()
    payment_processor = StripePaymentProcessor(settings.stripe_api_key) if settings.stripe_api_key else MockPaymentProcessor()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="AgentFabric production API with Postgres/migrations queue auth and billing integrations.",
        lifespan=lifespan,
    )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(_: Request, exc: ValidationError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(NotFoundError)
    async def not_found_error_handler(_: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def conflict_error_handler(_: Request, exc: ConflictError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

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
        if request.url.path in {
            "/",
            "/health",
            "/ready",
            "/favicon.ico",
            "/auth/principals/register",
            "/auth/token/issue",
            "/openapi.json",
            "/docs",
            "/redoc",
            "/forge",
        }:
            return await call_next(request)
        try:
            token = AuthService.parse_bearer_header(request.headers.get("Authorization"))
            with session_factory() as db:
                request.state.principal = auth.authenticate(db, token)
            return await call_next(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health():
        return HealthResponse()

    @app.get("/ready", tags=["system"])
    def ready(db: Session = Depends(get_db)):
        try:
            db.execute(text("SELECT 1"))
        except Exception:
            raise HTTPException(status_code=503, detail="database unavailable")
        if settings.redis_url.startswith("redis://"):
            try:
                import redis
                r = redis.from_url(settings.redis_url)
                r.ping()
            except Exception:
                raise HTTPException(status_code=503, detail="redis unavailable")
        return {"status": "ready"}

    @app.get("/", tags=["system"])
    def root():
        return {
            "service": "AgentFabric",
            "message": "API is running. Open /docs for interactive API documentation.",
            "docs": "/docs",
            "forge": "/forge",
            "health": "/health",
            "openapi": "/openapi.json",
        }

    @app.get("/forge", response_class=HTMLResponse, include_in_schema=False)
    def forge_interface():
        return render_forge_ui()

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        from fastapi.responses import Response
        return Response(status_code=204)

    @app.post("/auth/principals/register", tags=["auth"])
    def register_principal(payload: RegisterPrincipalRequest, db: Session = Depends(get_db)):
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
    def issue_token(payload: IssueTokenRequest, db: Session = Depends(get_db)):
        token, ttl = auth.issue_token(db, principal_id=payload.principal_id, ttl_seconds=payload.ttl_seconds)
        return TokenResponse(access_token=token, expires_in=ttl)

    @app.post("/auth/token/rotate", response_model=TokenResponse, tags=["auth"])
    def rotate_token(payload: RotateTokenRequest, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, [])
        token = AuthService.parse_bearer_header(request.headers.get("Authorization"))
        new_token, ttl = auth.rotate_token(db, bearer_token=token, ttl_seconds=payload.ttl_seconds)
        return TokenResponse(access_token=new_token, expires_in=ttl)

    @app.post("/registry/publish", response_model=PackageResponse, tags=["registry"])
    def publish_package(payload: PublishPackageRequest, request: Request, db: Session = Depends(get_db)):
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
        return PackageResponse(
            fqid=f"{package.namespace}/{package.package_id}:{package.version}",
            payload_digest=package.payload_digest,
        )

    @app.get("/registry/list", response_model=ListPackagesResponse, tags=["registry"])
    def list_packages(
        request: Request,
        query: Optional[str] = None,
        category: Optional[str] = None,
        permission: Optional[list[str]] = None,
        page: int = 1,
        page_size: int = 20,
        private_only: bool = False,
        db: Session = Depends(get_db),
    ):
        require_scopes(request, ["registry.read"])
        namespace_filter = None
        if private_only:
            require_scopes(request, ["registry.read_private"])
            namespace_filter = getattr(request.state.principal, "tenant_id", None)
        service = PackageService(db, signing_verifier=signing_verifier)
        result = service.list_packages(
            query=query,
            category=category,
            required_permissions=set(permission or []),
            page=page,
            page_size=page_size,
            namespace_filter=namespace_filter,
        )
        return ListPackagesResponse(**result)

    @app.post("/registry/install", tags=["registry"])
    def install_package(payload: InstallPackageRequest, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["registry.install"], tenant_id=payload.tenant_id)
        service = PackageService(db, signing_verifier=signing_verifier)
        install = service.install(
            tenant_id=payload.tenant_id,
            user_id=payload.user_id,
            namespace=payload.namespace,
            package_id=payload.package_id,
            version=payload.version,
        )
        return {"id": install.id, "package_fqid": install.package_fqid}

    @app.get("/registry/packages/{fqid}/reviews/summary", response_model=ReviewSummaryResponse, tags=["registry"])
    def get_review_summary(fqid: str, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["registry.read"])
        review_svc = ReviewService(db)
        return ReviewSummaryResponse(**review_svc.get_summary(fqid))

    @app.get("/registry/packages/{fqid}/reviews", tags=["registry"])
    def list_reviews(fqid: str, page: int = 1, page_size: int = 20, request: Request = None, db: Session = Depends(get_db)):
        require_scopes(request, ["registry.read"])
        review_svc = ReviewService(db)
        return review_svc.list_reviews(fqid, page=page, page_size=page_size)

    @app.post("/registry/packages/{fqid}/reviews", tags=["registry"])
    def submit_review(fqid: str, payload: SubmitReviewRequest, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["registry.read"], tenant_id=payload.tenant_id)
        review_svc = ReviewService(db)
        review_svc.submit(tenant_id=payload.tenant_id, user_id=payload.user_id, package_fqid=fqid, stars=payload.stars, review_text=payload.review_text)
        return {"status": "created"}

    @app.post("/projects", response_model=AgentProjectResponse, tags=["projects"])
    def create_project(payload: CreateAgentProjectRequest, request: Request, db: Session = Depends(get_db)):
        principal = require_scopes(request, ["projects.manage"], tenant_id=payload.namespace)
        project_svc = AgentProjectService(db)
        project_svc.create_project(
            namespace=payload.namespace,
            project_id=payload.project_id,
            display_name=payload.display_name,
            description=payload.description,
            created_by=principal.principal_id,
            contribution_zones=payload.contribution_zones,
            merge_policy=payload.merge_policy,
        )
        return AgentProjectResponse(**project_svc.get_project_detail(namespace=payload.namespace, project_id=payload.project_id))

    @app.get("/projects", response_model=ListAgentProjectsResponse, tags=["projects"])
    def list_projects(
        request: Request,
        namespace: Optional[str] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        db: Session = Depends(get_db),
    ):
        require_scopes(request, ["projects.read"])
        project_svc = AgentProjectService(db)
        return ListAgentProjectsResponse(**project_svc.list_projects(namespace=namespace, query=query, page=page, page_size=page_size))

    @app.get("/projects/{namespace}/{project_id}", response_model=AgentProjectResponse, tags=["projects"])
    def get_project(namespace: str, project_id: str, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["projects.read"])
        project_svc = AgentProjectService(db)
        return AgentProjectResponse(**project_svc.get_project_detail(namespace=namespace, project_id=project_id))

    @app.post("/projects/{namespace}/{project_id}/maintainers", tags=["projects"])
    def add_project_maintainer(
        namespace: str,
        project_id: str,
        payload: AddMaintainerRequest,
        request: Request,
        db: Session = Depends(get_db),
    ):
        principal = require_scopes(request, ["projects.manage"], tenant_id=namespace)
        project_svc = AgentProjectService(db)
        project_svc.add_maintainer(
            namespace=namespace,
            project_id=project_id,
            actor_id=principal.principal_id,
            principal_id=payload.principal_id,
        )
        return {"status": "added"}

    @app.post("/projects/{namespace}/{project_id}/branches", tags=["projects"])
    def create_project_branch(
        namespace: str,
        project_id: str,
        payload: CreateBranchRequest,
        request: Request,
        db: Session = Depends(get_db),
    ):
        principal = require_scopes(request, ["projects.manage"], tenant_id=namespace)
        project_svc = AgentProjectService(db)
        branch = project_svc.create_branch(
            namespace=namespace,
            project_id=project_id,
            actor_id=principal.principal_id,
            branch_name=payload.branch_name,
            base_ref=payload.base_ref,
        )
        return {"branch_name": branch.branch_name, "base_ref": branch.base_ref, "status": branch.status}

    @app.post("/projects/{namespace}/{project_id}/contributions", response_model=ContributionResponse, tags=["projects"])
    def submit_contribution(
        namespace: str,
        project_id: str,
        payload: SubmitContributionRequest,
        request: Request,
        db: Session = Depends(get_db),
    ):
        principal = require_scopes(request, ["projects.contribute"])
        project_svc = AgentProjectService(db)
        contribution = project_svc.submit_contribution(
            namespace=namespace,
            project_id=project_id,
            submitter_id=principal.principal_id,
            branch_name=payload.branch_name,
            title=payload.title,
            summary=payload.summary,
            contribution_zone=payload.contribution_zone,
            contribution_manifest=payload.contribution_manifest,
            metrics=payload.metrics,
            regressions=payload.regressions,
        )
        return ContributionResponse(contribution_id=contribution.id, status=contribution.status)

    @app.get("/projects/{namespace}/{project_id}/contributions", response_model=ListContributionsResponse, tags=["projects"])
    def list_contributions(
        namespace: str,
        project_id: str,
        request: Request,
        status: Optional[str] = None,
        limit: int = 50,
        db: Session = Depends(get_db),
    ):
        require_scopes(request, ["projects.read"])
        project_svc = AgentProjectService(db)
        return project_svc.list_contributions(namespace=namespace, project_id=project_id, status=status, limit=limit)

    @app.post("/projects/{namespace}/{project_id}/contributions/{contribution_id}/evaluate", tags=["projects"])
    def evaluate_contribution(
        namespace: str,
        project_id: str,
        contribution_id: int,
        request: Request,
        db: Session = Depends(get_db),
    ):
        require_scopes(request, ["projects.evaluate"])
        project_svc = AgentProjectService(db)
        return project_svc.evaluate_contribution(namespace=namespace, project_id=project_id, contribution_id=contribution_id)

    @app.post("/projects/{namespace}/{project_id}/contributions/{contribution_id}/review", tags=["projects"])
    def review_contribution(
        namespace: str,
        project_id: str,
        contribution_id: int,
        payload: ReviewContributionRequest,
        request: Request,
        db: Session = Depends(get_db),
    ):
        principal = require_scopes(request, ["projects.manage"], tenant_id=namespace)
        project_svc = AgentProjectService(db)
        return project_svc.review_contribution(
            namespace=namespace,
            project_id=project_id,
            contribution_id=contribution_id,
            reviewer_id=principal.principal_id,
            decision=payload.decision,
            decision_notes=payload.decision_notes,
            release_version=payload.release_version,
            release_channel=payload.release_channel,
        )

    @app.get("/projects/{namespace}/{project_id}/releases", tags=["projects"])
    def list_project_releases(
        namespace: str,
        project_id: str,
        request: Request,
        channel: Optional[str] = None,
        db: Session = Depends(get_db),
    ):
        require_scopes(request, ["projects.read"])
        project_svc = AgentProjectService(db)
        return {"items": project_svc.list_releases(namespace=namespace, project_id=project_id, channel=channel)}

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

    @app.post("/queue/dequeue", response_model=Optional[QueueMessageResponse], tags=["queue"])
    def dequeue_job(queue_name: str, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["queue.read"])
        service = QueueService(db, backend=queue_backend)
        item = service.dequeue(queue_name)
        if item is None:
            return None
        return QueueMessageResponse(
            message_id=item.message_id,
            queue_name=item.queue_name,
            status="done",
            payload=item.payload,
            attempts=item.attempts,
            created_at=item.created_at,
        )

    @app.post("/audit/append", tags=["audit"])
    def append_audit(actor_id: str, action: str, target: str, metadata: Optional[dict], request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["audit.write"])
        service = AuditService(db)
        return service.append(actor_id=actor_id, action=action, target=target, metadata=metadata)

    @app.get("/audit/export", tags=["audit"])
    def export_audit(since_id: int = 0, limit: int = 1000, request: Request = None, db: Session = Depends(get_db)):
        require_scopes(request, ["audit.export"])
        from agentfabric.server.models import AuditEvent
        stmt = select(AuditEvent).where(AuditEvent.id > since_id).order_by(AuditEvent.id).limit(limit)
        rows = db.execute(stmt).scalars().all()
        return {"events": [{"id": r.id, "actor_id": r.actor_id, "action": r.action, "target": r.target, "metadata": r.metadata_json, "event_hash": r.event_hash, "created_at": r.created_at.isoformat()} for r in rows]}

    @app.post("/workflows/run", tags=["workflows"])
    def run_workflow(payload: WorkflowRunRequest, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["runtime.run"])
        from agentfabric.phase3.workflow import WorkflowEngine, WorkflowNode
        nodes = [WorkflowNode(node_id=n["node_id"], agent_name=n["agent_name"], dependencies=tuple(n.get("dependencies", [])), max_retries=n.get("max_retries", 0), timeout_seconds=n.get("timeout_seconds", 30.0)) for n in payload.nodes]
        engine = WorkflowEngine()
        def stub_runner(node, node_input):
            return {"node_id": node.node_id, "context": node_input.get("context", {})}
        result = engine.run(workflow_id=payload.workflow_id, idempotency_key=payload.idempotency_key, nodes=nodes, initial_payload=payload.initial_payload, node_runner=stub_runner)
        return result

    @app.post("/admin/principals/{principal_id}/role", tags=["admin"])
    def assign_role(principal_id: str, payload: AssignRoleRequest, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["rbac.assign_role"])
        from agentfabric.server.models import Principal
        from agentfabric.phase4.rbac import RbacService
        if payload.role not in RbacService.ROLE_PERMISSIONS:
            raise HTTPException(status_code=400, detail=f"unknown role: {payload.role}")
        principal = db.get(Principal, principal_id)
        if not principal:
            raise HTTPException(status_code=404, detail="principal not found")
        principal.role = payload.role
        db.add(principal)
        db.flush()
        return {"principal_id": principal_id, "role": payload.role}

    return app
