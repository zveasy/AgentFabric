"""FastAPI application with auth middleware and OpenAPI docs."""

from __future__ import annotations

from contextlib import asynccontextmanager
import shutil

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentfabric.server.auth import AuthService, require_scopes
from agentfabric.server.config import Settings, get_settings
from agentfabric.server.database import build_session_factory, run_migrations
from agentfabric.server.models import Principal
from agentfabric.server.payments import MockPaymentProcessor, StripePaymentProcessor, parse_stripe_webhook_event
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
    if settings.auto_migrate:
        run_migrations(settings.database_url)
    session_factory, _ = build_session_factory(settings)
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

    @app.get("/metrics/prometheus", tags=["system"])
    def metrics(request: Request):
        require_scopes(request, ["metrics.read"])
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/audit/append", tags=["audit"])
    def append_audit(actor_id: str, action: str, target: str, metadata: dict | None, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["audit.write"])
        service = AuditService(db)
        return service.append(actor_id=actor_id, action=action, target=target, metadata=metadata)

    return app
