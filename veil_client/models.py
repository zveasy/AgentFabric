from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SanitizeContextRequest:
    agent_id: str
    tenant_id: str
    context: dict[str, object]


@dataclass(frozen=True)
class SanitizeContextResponse:
    sanitized_context: dict[str, object]
    redactions: tuple[str, ...] = ()


@dataclass(frozen=True)
class PolicyCheckRequest:
    agent_id: str
    action: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyCheckResponse:
    allowed: bool
    reason: str = ""


@dataclass(frozen=True)
class RestoreRequest:
    agent_id: str
    restore_token: str
    justification: str


@dataclass(frozen=True)
class RestoreResponse:
    approved: bool
    restored_context: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditEventRequest:
    agent_id: str
    event_type: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditEventResponse:
    event_id: str
    accepted: bool


@dataclass(frozen=True)
class ToolVerificationRequest:
    agent_id: str
    tool_name: str
    tool_input: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolVerificationResponse:
    allowed: bool
    reason: str = ""


@dataclass(frozen=True)
class TokenIssueRequest:
    agent_id: str
    scopes: tuple[str, ...] = ()
    ttl_seconds: int = 300


@dataclass(frozen=True)
class TokenIssueResponse:
    token: str
    expires_in_seconds: int
