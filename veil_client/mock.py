from __future__ import annotations

from .models import (
    AuditEventRequest,
    AuditEventResponse,
    PolicyCheckRequest,
    PolicyCheckResponse,
    RestoreRequest,
    RestoreResponse,
    SanitizeContextRequest,
    SanitizeContextResponse,
    ToolVerificationRequest,
    ToolVerificationResponse,
    TokenIssueRequest,
    TokenIssueResponse,
)


class MockVeilClient:
    """Deterministic mock client for unit tests and early integration work."""

    def sanitize_context(self, request: SanitizeContextRequest) -> SanitizeContextResponse:
        return SanitizeContextResponse(sanitized_context=dict(request.context))

    def check_policy(self, request: PolicyCheckRequest) -> PolicyCheckResponse:
        return PolicyCheckResponse(allowed=True)

    def request_restore(self, request: RestoreRequest) -> RestoreResponse:
        return RestoreResponse(approved=False)

    def create_audit_event(self, request: AuditEventRequest) -> AuditEventResponse:
        return AuditEventResponse(event_id=f"audit:{request.agent_id}:{request.event_type}", accepted=True)

    def verify_tool_action(self, request: ToolVerificationRequest) -> ToolVerificationResponse:
        return ToolVerificationResponse(allowed=True)

    def issue_agent_token(self, request: TokenIssueRequest) -> TokenIssueResponse:
        return TokenIssueResponse(token=f"mock-token:{request.agent_id}", expires_in_seconds=request.ttl_seconds)
