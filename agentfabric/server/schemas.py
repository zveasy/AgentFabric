"""Pydantic schemas for FastAPI request/response bodies."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class ReadinessCheckResponse(BaseModel):
    name: str
    ok: bool
    detail: str = ""


class ReadinessResponse(BaseModel):
    status: str
    checks: list[ReadinessCheckResponse] = Field(default_factory=list)


class RegisterPrincipalRequest(BaseModel):
    principal_id: str
    tenant_id: str
    principal_type: str = "user"
    role: str = "viewer"
    scopes: list[str] = Field(default_factory=list)


class IssueTokenRequest(BaseModel):
    principal_id: str
    ttl_seconds: int = 3600


class RotateTokenRequest(BaseModel):
    ttl_seconds: int = 3600


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class PublishPackageRequest(BaseModel):
    namespace: str
    package_id: str
    version: str
    category: str
    permissions: list[str] = Field(default_factory=list)
    manifest: dict
    payload: str
    signature: str
    signer_id: str


class PackageResponse(BaseModel):
    fqid: str
    payload_digest: str


class ListPackagesResponse(BaseModel):
    items: list[dict]
    total: int
    page: int
    page_size: int
    total_pages: int


class InstallPackageRequest(BaseModel):
    tenant_id: str
    user_id: str
    namespace: str
    package_id: str
    version: Optional[str] = None


class BillingEventRequest(BaseModel):
    tenant_id: str
    actor_id: str
    event_type: str
    package_fqid: str
    idempotency_key: str


class InvoiceResponse(BaseModel):
    tenant_id: str
    lines: list[dict]
    total: float


class QueueEnqueueRequest(BaseModel):
    queue_name: str
    payload: dict


class QueueMessageResponse(BaseModel):
    message_id: str
    queue_name: str
    status: str
    payload: dict
    attempts: int
    created_at: datetime


class QueueMessageListResponse(BaseModel):
    items: list[QueueMessageResponse]


class ReplayDlqRequest(BaseModel):
    queue_name: str
    limit: int = 100


class ReplayDlqResponse(BaseModel):
    queue_name: str
    source_queue: str
    replayed: int
    message_ids: list[str] = Field(default_factory=list)


class AuditIntegrityResponse(BaseModel):
    ok: bool


class RuntimeInstallRequest(BaseModel):
    manifest: dict
    payload: str
    signer_id: str
    signer_key: str
    signature: str


class RuntimeAgentRefRequest(BaseModel):
    agent_id: str


class RuntimeRunRequest(BaseModel):
    agent_id: str
    request: dict
    user_id: str
    session_id: str


class EnterpriseAssignRoleRequest(BaseModel):
    principal_id: str
    role: str


class EnterprisePermissionCheckRequest(BaseModel):
    principal_id: str
    permission: str


class NamespaceCreateRequest(BaseModel):
    owner_tenant_id: str
    namespace: str


class NamespaceGrantRequest(BaseModel):
    owner_tenant_id: str
    namespace: str
    target_tenant_id: str


class NamespaceCheckRequest(BaseModel):
    tenant_id: str
    namespace: str


class EnterpriseAuditAppendRequest(BaseModel):
    actor_id: str
    action: str
    target: str
    metadata: dict = Field(default_factory=dict)


class EnterpriseAuditExportRequest(BaseModel):
    output_file: str


class ReviewSubmitRequest(BaseModel):
    tenant_id: str
    package_fqid: str
    user_id: str
    stars: int
    review: str


class ReviewResolveRequest(BaseModel):
    review_id: int
    approved: bool


class GdprDeletionRequest(BaseModel):
    tenant_id: str
    user_id: str | None = None
    reason: str


class LegalPublishRequest(BaseModel):
    doc_type: str
    version: str
    content: str


class LegalAcceptRequest(BaseModel):
    doc_type: str
    principal_id: str


class SubmitReviewRequest(BaseModel):
    tenant_id: str
    user_id: str
    stars: int
    review_text: str = ""


class ReviewSummaryResponse(BaseModel):
    count: int
    avg_stars: float


class WorkflowRunRequest(BaseModel):
    workflow_id: str
    idempotency_key: str
    nodes: list[dict]
    initial_payload: dict = Field(default_factory=dict)


class AssignRoleRequest(BaseModel):
    role: str
