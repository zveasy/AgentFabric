"""Pydantic schemas for FastAPI request/response bodies."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"


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


class CreateAgentProjectRequest(BaseModel):
    namespace: str
    project_id: str
    display_name: str
    description: str = ""
    contribution_zones: list[str] = Field(default_factory=list)
    merge_policy: dict = Field(default_factory=dict)


class AgentProjectResponse(BaseModel):
    namespace: str
    project_id: str
    display_name: str
    description: str
    default_branch: str
    contribution_zones: list[str]
    merge_policy: dict
    maintainers: list[str]
    branches: list[dict]
    releases: list[dict]
    created_by: str
    created_at: str


class ListAgentProjectsResponse(BaseModel):
    items: list[dict]
    total: int
    page: int
    page_size: int
    total_pages: int


class AddMaintainerRequest(BaseModel):
    principal_id: str


class CreateBranchRequest(BaseModel):
    branch_name: str
    base_ref: str = "main"


class SubmitContributionRequest(BaseModel):
    branch_name: str
    title: str
    summary: str = ""
    contribution_zone: str
    contribution_manifest: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)
    regressions: dict = Field(default_factory=dict)


class ContributionResponse(BaseModel):
    contribution_id: int
    status: str


class ReviewContributionRequest(BaseModel):
    decision: str
    decision_notes: str = ""
    release_version: Optional[str] = None
    release_channel: str = "stable"


class ListContributionsResponse(BaseModel):
    items: list[dict]
    total: int
