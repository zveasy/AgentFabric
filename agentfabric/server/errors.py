"""Structured API error responses."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from agentfabric.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError


ERROR_CODES = {
    400: "validation_error",
    401: "auth_failure",
    403: "rbac_or_tenant_denial",
    404: "not_found",
    409: "conflict_or_quota_exceeded",
    500: "internal_error",
    503: "service_unavailable",
}


@dataclass(frozen=True)
class ApiError:
    code: str
    message: str
    status: int

    def as_dict(self) -> dict[str, object]:
        return {"error": {"code": self.code, "message": self.message, "status": self.status}}


def error_response(status_code: int, message: str, code: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=ApiError(code or ERROR_CODES.get(status_code, "error"), message, status_code).as_dict())


def http_exception_response(exc: HTTPException) -> JSONResponse:
    return error_response(exc.status_code, str(exc.detail), ERROR_CODES.get(exc.status_code))


def domain_exception_response(exc: Exception) -> JSONResponse:
    if isinstance(exc, AuthorizationError):
        return error_response(403, str(exc), "rbac_or_tenant_denial")
    if isinstance(exc, NotFoundError):
        return error_response(404, str(exc), "not_found")
    if isinstance(exc, ConflictError):
        return error_response(409, str(exc), "conflict_or_quota_exceeded")
    if isinstance(exc, ValidationError):
        return error_response(400, str(exc), "validation_error")
    return error_response(400, str(exc), "agentfabric_error")
