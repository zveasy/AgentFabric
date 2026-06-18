"""The exclusive VEIL integration boundary for AgentFabric."""

from .exceptions import VeilClientError
from .interfaces import VeilClient
from .mock import MockVeilClient
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

__all__ = [
    "AuditEventRequest",
    "AuditEventResponse",
    "MockVeilClient",
    "PolicyCheckRequest",
    "PolicyCheckResponse",
    "RestoreRequest",
    "RestoreResponse",
    "SanitizeContextRequest",
    "SanitizeContextResponse",
    "ToolVerificationRequest",
    "ToolVerificationResponse",
    "TokenIssueRequest",
    "TokenIssueResponse",
    "VeilClient",
    "VeilClientError",
]
