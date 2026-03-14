"""FastAPI application with auth middleware and OpenAPI docs."""

from __future__ import annotations

from contextlib import asynccontextmanager
import shutil

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentfabric.errors import AgentFabricError, AuthorizationError, ConflictError, NotFoundError, ValidationError
from agentfabric.phase2.models import Rating
from agentfabric.production.control_plane import ProductionControlPlane
from agentfabric.server.auth import AuthService, require_scopes
from agentfabric.server.config import Settings, get_settings
from agentfabric.server.database import build_session_factory, run_migrations
from agentfabric.server.models import Principal
from agentfabric.server.payments import MockPaymentProcessor, StripePaymentProcessor, parse_stripe_webhook_event
from agentfabric.server.queue import InMemoryQueueBackend, RedisQueueBackend
from agentfabric.server.schemas import (
    AuditIntegrityResponse,
    BillingEventRequest,
    EnterpriseAssignRoleRequest,
    EnterpriseAuditAppendRequest,
    EnterpriseAuditExportRequest,
    EnterprisePermissionCheckRequest,
    GdprDeletionRequest,
    HealthResponse,
    InstallPackageRequest,
    InvoiceResponse,
    IssueTokenRequest,
    LegalAcceptRequest,
    LegalPublishRequest,
    ListPackagesResponse,
    NamespaceCheckRequest,
    NamespaceCreateRequest,
    NamespaceGrantRequest,
    PackageResponse,
    PublishPackageRequest,
    QueueEnqueueRequest,
    QueueMessageListResponse,
    QueueMessageResponse,
    ReadinessCheckResponse,
    ReadinessResponse,
    RegisterPrincipalRequest,
    ReviewResolveRequest,
    ReviewSubmitRequest,
    RuntimeAgentRefRequest,
    RuntimeInstallRequest,
    RuntimeRunRequest,
    ReplayDlqRequest,
    ReplayDlqResponse,
    RotateTokenRequest,
    TokenResponse,
)
from agentfabric.server.services import AuditService, BillingService, PackageService, QueueService
from agentfabric.server.signing import CosignVerifier, DigestFallbackVerifier

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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.environment.lower() in {"production", "staging"}:
        if settings.jwt_secret == "change-me-in-production":
            raise RuntimeError("AGENTFABRIC_JWT_SECRET must be explicitly configured for production-like environments")
        if not settings.bootstrap_token:
            raise RuntimeError("AGENTFABRIC_BOOTSTRAP_TOKEN must be configured for production-like environments")
    if settings.auto_migrate:
        run_migrations(settings.database_url)
    session_factory, _ = build_session_factory(settings)
    control_plane = ProductionControlPlane(db_path=settings.production_db_path, database_url=settings.database_url)
    auth = AuthService(settings)
    queue_backend = choose_queue_backend(settings)
    signing_verifier = choose_signing_verifier(settings)
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

    @app.exception_handler(AuthorizationError)
    async def _handle_authz_error(_: Request, exc: AuthorizationError):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(NotFoundError)
    async def _handle_not_found(_: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def _handle_conflict(_: Request, exc: ConflictError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ValidationError)
    async def _handle_validation(_: Request, exc: ValidationError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(AgentFabricError)
    async def _handle_agentfabric(_: Request, exc: AgentFabricError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

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
            "/health",
            "/health/ready",
            "/auth/principals/register",
            "/auth/token/issue",
            "/billing/webhooks/stripe",
            "/openapi.json",
            "/docs",
            "/redoc",
        }:
            return await call_next(request)
        try:
            token = AuthService.parse_bearer_header(request.headers.get("Authorization"))
            with session_factory() as db:
                request.state.principal = auth.authenticate(db, token)
            return await call_next(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

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

    @app.get("/health/ready", response_model=ReadinessResponse, tags=["system"])
    def readiness(db: Session = Depends(get_db)):
        checks: list[ReadinessCheckResponse] = []

        try:
            db.execute(select(1)).scalar_one()
            checks.append(ReadinessCheckResponse(name="database", ok=True))
        except Exception as exc:
            checks.append(ReadinessCheckResponse(name="database", ok=False, detail=str(exc)))

        queue_ok = queue_backend.healthcheck()
        queue_detail = f"backend={queue_backend.__class__.__name__}"
        if not queue_ok:
            queue_detail = f"{queue_detail}; not reachable"
        checks.append(ReadinessCheckResponse(name="queue", ok=queue_ok, detail=queue_detail))

        try:
            audit_ok = control_plane.verify_audit_integrity()
            checks.append(
                ReadinessCheckResponse(
                    name="audit_chain",
                    ok=audit_ok,
                    detail="" if audit_ok else "audit chain verification failed",
                )
            )
        except Exception as exc:
            checks.append(ReadinessCheckResponse(name="audit_chain", ok=False, detail=str(exc)))

        signing_ok = not settings.strict_signing or shutil.which("cosign") is not None
        signing_detail = "strict signing disabled"
        if settings.strict_signing:
            signing_detail = "cosign available" if signing_ok else "strict signing enabled but cosign missing"
        checks.append(ReadinessCheckResponse(name="signing", ok=signing_ok, detail=signing_detail))

        ready = all(item.ok for item in checks)
        response = ReadinessResponse(status="ok" if ready else "degraded", checks=checks)
        if ready:
            return response
        return JSONResponse(status_code=503, content=response.model_dump())

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
        )
        return {"principal_id": principal.principal_id, "tenant_id": principal.tenant_id}

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
        query: str | None = None,
        category: str | None = None,
        permission: list[str] | None = None,
        page: int = 1,
        page_size: int = 20,
        db: Session = Depends(get_db),
    ):
        require_scopes(request, ["registry.read"])
        service = PackageService(db, signing_verifier=signing_verifier)
        result = service.list_packages(
            query=query,
            category=category,
            required_permissions=set(permission or []),
            page=page,
            page_size=page_size,
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

    @app.get("/queue/messages", response_model=QueueMessageListResponse, tags=["queue"])
    def queue_messages(queue_name: str, request: Request, status: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
        require_scopes(request, ["queue.read"])
        service = QueueService(db, backend=queue_backend)
        messages = service.list_messages(queue_name, status=status, limit=limit)
        return QueueMessageListResponse(
            items=[
                QueueMessageResponse(
                    message_id=item["message_id"],
                    queue_name=item["queue_name"],
                    status=item["status"],
                    payload=item["payload"],
                    attempts=item["attempts"],
                    created_at=item["created_at"],
                )
                for item in messages
            ]
        )

    @app.post("/queue/replay-dlq", response_model=ReplayDlqResponse, tags=["queue"])
    def replay_dlq(payload: ReplayDlqRequest, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["queue.write"])
        service = QueueService(db, backend=queue_backend)
        result = service.replay_dlq(payload.queue_name, limit=payload.limit)
        return ReplayDlqResponse(**result)

    @app.get("/metrics/prometheus", tags=["system"])
    def metrics(request: Request):
        require_scopes(request, ["metrics.read"])
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/runtime/agents", tags=["runtime"])
    def runtime_agents(request: Request):
        require_scopes(request, ["runtime.read"])
        return {"items": control_plane.runtime_agents()}

    @app.post("/runtime/install", tags=["runtime"])
    def runtime_install(payload: RuntimeInstallRequest, request: Request):
        require_scopes(request, ["runtime.install"])
        agent_id = control_plane.install_runtime_agent(
            manifest=payload.manifest,
            payload=payload.payload.encode("utf-8"),
            signer_id=payload.signer_id,
            signer_key=payload.signer_key,
            signature=payload.signature,
        )
        return {"agent_id": agent_id}

    @app.post("/runtime/load", tags=["runtime"])
    def runtime_load(payload: RuntimeAgentRefRequest, request: Request):
        require_scopes(request, ["runtime.run"])
        control_plane.runtime_load(payload.agent_id)
        return {"status": "loaded"}

    @app.post("/runtime/run", tags=["runtime"])
    def runtime_run(payload: RuntimeRunRequest, request: Request):
        require_scopes(request, ["runtime.run"])
        return control_plane.runtime_run(
            agent_id=payload.agent_id,
            request=payload.request,
            user_id=payload.user_id,
            session_id=payload.session_id,
        )

    @app.post("/runtime/suspend", tags=["runtime"])
    def runtime_suspend(payload: RuntimeAgentRefRequest, request: Request):
        require_scopes(request, ["runtime.run"])
        control_plane.runtime_suspend(payload.agent_id)
        return {"status": "suspended"}

    @app.post("/runtime/uninstall", tags=["runtime"])
    def runtime_uninstall(payload: RuntimeAgentRefRequest, request: Request):
        require_scopes(request, ["runtime.install"])
        control_plane.runtime_uninstall(payload.agent_id)
        return {"status": "uninstalled"}

    @app.post("/enterprise/rbac/assign", tags=["enterprise"])
    def enterprise_rbac_assign(payload: EnterpriseAssignRoleRequest, request: Request):
        require_scopes(request, ["enterprise.rbac.write"])
        control_plane.assign_role(payload.principal_id, payload.role)
        return {"status": "ok"}

    @app.post("/enterprise/rbac/check", tags=["enterprise"])
    def enterprise_rbac_check(payload: EnterprisePermissionCheckRequest, request: Request):
        require_scopes(request, ["enterprise.rbac.read"])
        control_plane.check_permission(payload.principal_id, payload.permission)
        return {"allowed": True}

    @app.post("/enterprise/namespace/create", tags=["enterprise"])
    def enterprise_namespace_create(payload: NamespaceCreateRequest, request: Request):
        require_scopes(request, ["enterprise.namespace.write"], tenant_id=payload.owner_tenant_id)
        control_plane.create_namespace(payload.owner_tenant_id, payload.namespace)
        return {"status": "created"}

    @app.post("/enterprise/namespace/grant", tags=["enterprise"])
    def enterprise_namespace_grant(payload: NamespaceGrantRequest, request: Request):
        require_scopes(request, ["enterprise.namespace.write"], tenant_id=payload.owner_tenant_id)
        control_plane.grant_namespace_access(
            payload.owner_tenant_id,
            payload.namespace,
            payload.target_tenant_id,
        )
        return {"status": "granted"}

    @app.post("/enterprise/namespace/check", tags=["enterprise"])
    def enterprise_namespace_check(payload: NamespaceCheckRequest, request: Request):
        require_scopes(request, ["enterprise.namespace.read"], tenant_id=payload.tenant_id)
        control_plane.check_namespace_access(payload.tenant_id, payload.namespace)
        return {"allowed": True}

    @app.post("/enterprise/audit/append", tags=["enterprise"])
    def enterprise_audit_append(payload: EnterpriseAuditAppendRequest, request: Request):
        require_scopes(request, ["enterprise.audit.write"])
        return control_plane.append_audit(
            actor_id=payload.actor_id,
            action=payload.action,
            target=payload.target,
            metadata=payload.metadata,
        )

    @app.post("/enterprise/audit/export", tags=["enterprise"])
    def enterprise_audit_export(payload: EnterpriseAuditExportRequest, request: Request):
        require_scopes(request, ["enterprise.audit.read"])
        path = control_plane.export_siem_audit(payload.output_file)
        return {"path": path}

    @app.get("/enterprise/audit/integrity", response_model=AuditIntegrityResponse, tags=["enterprise"])
    def enterprise_audit_integrity(request: Request):
        require_scopes(request, ["enterprise.audit.read"])
        return AuditIntegrityResponse(ok=control_plane.verify_audit_integrity())

    @app.post("/reviews/submit", tags=["reviews"])
    def reviews_submit(payload: ReviewSubmitRequest, request: Request):
        require_scopes(request, ["reviews.write"], tenant_id=payload.tenant_id)
        review_id = control_plane.submit_review(
            Rating(
                tenant_id=payload.tenant_id,
                package_fqid=payload.package_fqid,
                user_id=payload.user_id,
                stars=int(payload.stars),
                review=payload.review,
            )
        )
        return {"review_id": review_id}

    @app.post("/reviews/moderation/pending", tags=["reviews"])
    def reviews_pending(request: Request):
        require_scopes(request, ["reviews.moderate"])
        return {"items": control_plane.pending_reviews()}

    @app.post("/reviews/moderation/resolve", tags=["reviews"])
    def reviews_resolve(payload: ReviewResolveRequest, request: Request):
        require_scopes(request, ["reviews.moderate"])
        control_plane.moderate_review(payload.review_id, approved=payload.approved)
        return {"status": "ok"}

    @app.post("/compliance/gdpr/request", tags=["compliance"])
    def gdpr_request(payload: GdprDeletionRequest, request: Request):
        require_scopes(request, ["compliance.gdpr.write"], tenant_id=payload.tenant_id)
        request_id = control_plane.request_gdpr_deletion(
            tenant_id=payload.tenant_id,
            user_id=payload.user_id,
            reason=payload.reason,
        )
        return {"request_id": request_id}

    @app.post("/compliance/gdpr/process", tags=["compliance"])
    def gdpr_process(request: Request):
        require_scopes(request, ["compliance.gdpr.write"])
        return {"processed": control_plane.process_gdpr_deletions()}

    @app.post("/compliance/legal/publish", tags=["compliance"])
    def legal_publish(payload: LegalPublishRequest, request: Request):
        require_scopes(request, ["compliance.legal.write"])
        control_plane.publish_legal_document(
            payload.doc_type,
            payload.version,
            payload.content,
        )
        return {"status": "ok"}

    @app.post("/compliance/legal/accept", tags=["compliance"])
    def legal_accept(payload: LegalAcceptRequest, request: Request):
        require_scopes(request, ["compliance.legal.read"])
        return control_plane.accept_legal_document(payload.doc_type, payload.principal_id)

    @app.post("/ops/backup", tags=["ops"])
    def ops_backup(request: Request):
        require_scopes(request, ["ops.backup.write"])
        backup = control_plane.create_backup()
        return {"backup_file": backup}

    @app.post("/audit/append", tags=["audit"])
    def append_audit(actor_id: str, action: str, target: str, metadata: dict | None, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["audit.write"])
        service = AuditService(db)
        return service.append(actor_id=actor_id, action=action, target=target, metadata=metadata)

    return app
