from __future__ import annotations

from typing import Protocol

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


class VeilClient(Protocol):
    def sanitize_context(self, request: SanitizeContextRequest) -> SanitizeContextResponse:
        """Sanitize task or memory context before agent execution."""

    def check_policy(self, request: PolicyCheckRequest) -> PolicyCheckResponse:
        """Check whether an action is allowed under VEIL policy."""

    def request_restore(self, request: RestoreRequest) -> RestoreResponse:
        """Request restoration of previously protected context."""

    def create_audit_event(self, request: AuditEventRequest) -> AuditEventResponse:
        """Write an auditable event into VEIL."""

    def verify_tool_action(self, request: ToolVerificationRequest) -> ToolVerificationResponse:
        """Validate a tool action before execution."""

    def issue_agent_token(self, request: TokenIssueRequest) -> TokenIssueResponse:
        """Issue an agent-scoped token for VEIL-mediated operations."""
