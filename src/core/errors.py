"""RFC 7807 Problem Details models, domain exceptions, and error handlers."""

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.context import get_current_request_id

logger = logging.getLogger("medisync.errors")

RFC7807_MEDIA_TYPE = "application/problem+json"


class ProblemDetails(BaseModel):
    """RFC 7807 Problem Details representation."""

    type: str = Field(
        default="about:blank",
        description="URI reference identifying the problem type",
    )
    title: str = Field(description="Short human-readable summary of the problem type")
    status: int = Field(description="HTTP status code")
    detail: str = Field(
        description="Human-readable explanation specific to this occurrence"
    )
    instance: str | None = Field(
        default=None,
        description="URI reference identifying specific occurrence",
    )
    code: str | None = Field(
        default=None, description="Application-specific error code"
    )
    request_id: str | None = Field(default=None, description="Correlation / Request ID")
    invalid_params: list[dict[str, Any]] | None = Field(
        default=None,
        description="Validation errors breakdown for 422 responses",
    )


class DomainError(Exception):
    """Base class for all business and domain exceptions."""

    status_code: int = 400
    title: str = "Bad Request"
    error_type: str = "about:blank"
    code: str = "DOMAIN_ERROR"

    def __init__(
        self,
        detail: str,
        *,
        status_code: int | None = None,
        title: str | None = None,
        error_type: str | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        if title is not None:
            self.title = title
        if error_type is not None:
            self.error_type = error_type
        if code is not None:
            self.code = code


class NotFoundError(DomainError):
    status_code: int = 404
    title: str = "Not Found"
    code: str = "NOT_FOUND"


class ConflictError(DomainError):
    status_code: int = 409
    title: str = "Conflict"
    code: str = "CONFLICT"


class UnauthorizedError(DomainError):
    status_code: int = 401
    title: str = "Unauthorized"
    code: str = "UNAUTHORIZED"


class TokenRevogadoError(UnauthorizedError):
    """Raised when an access or refresh token has been revoked or reused."""

    title: str = "Token Revogado"
    code: str = "TOKEN_REVOGADO"

    def __init__(
        self, detail: str = "Sessão ou token de autenticação revogado."
    ) -> None:
        super().__init__(detail, title=self.title, code=self.code)


class ForbiddenError(DomainError):
    status_code: int = 403
    title: str = "Forbidden"
    code: str = "FORBIDDEN"


class BadRequestError(DomainError):
    status_code: int = 400
    title: str = "Bad Request"
    code: str = "BAD_REQUEST"


class ValidationError(DomainError):
    status_code: int = 422
    title: str = "Unprocessable Entity"
    code: str = "VALIDATION_ERROR"


class TenantInvalidoError(BadRequestError):
    """Raised when tenant context is missing or non-positive."""

    title = "Organização Inválida"
    code = "TENANT_INVALIDO"

    def __init__(
        self, detail: str = "Header X-Tenant-ID obrigatório e positivo."
    ) -> None:
        super().__init__(detail, title=self.title, code=self.code)


def create_problem_response(
    status: int,
    title: str,
    detail: str,
    *,
    error_type: str = "about:blank",
    instance: str | None = None,
    code: str | None = None,
    invalid_params: list[dict[str, Any]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Create a JSONResponse adhering strictly to RFC 7807."""
    req_id = get_current_request_id()
    problem = ProblemDetails(
        type=error_type,
        title=title,
        status=status,
        detail=detail,
        instance=instance,
        code=code,
        request_id=req_id,
        invalid_params=invalid_params,
    )
    resp_headers: dict[str, str] = dict(headers) if headers else {}
    if req_id:
        resp_headers["X-Request-ID"] = req_id

    return JSONResponse(
        status_code=status,
        content=problem.model_dump(exclude_none=True),
        media_type=RFC7807_MEDIA_TYPE,
        headers=resp_headers,
    )


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert DomainError into RFC 7807 problem details response."""
    if not isinstance(exc, DomainError):
        return await unhandled_exception_handler(request, exc)
    return create_problem_response(
        status=exc.status_code,
        title=exc.title,
        detail=exc.detail,
        error_type=exc.error_type,
        instance=request.url.path,
        code=exc.code,
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert FastAPI RequestValidationError into RFC 7807 problem details."""
    if not isinstance(exc, RequestValidationError):
        return await unhandled_exception_handler(request, exc)
    invalid_params: list[dict[str, Any]] = []
    for err in exc.errors():
        loc_str = " -> ".join(str(item) for item in err.get("loc", []))
        invalid_params.append(
            {
                "name": loc_str,
                "reason": err.get("msg", ""),
                "type": err.get("type", ""),
            }
        )

    return create_problem_response(
        status=422,
        title="Unprocessable Entity",
        detail="The request body or parameters failed validation.",
        error_type="about:blank",
        instance=request.url.path,
        code="VALIDATION_ERROR",
        invalid_params=invalid_params,
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert Starlette HTTPException into RFC 7807 problem details."""
    if not isinstance(exc, StarletteHTTPException):
        return await unhandled_exception_handler(request, exc)
    headers: Mapping[str, str] | None = getattr(exc, "headers", None)
    return create_problem_response(
        status=exc.status_code,
        title="HTTP Error",
        detail=str(exc.detail),
        instance=request.url.path,
        headers=headers,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled exceptions and return safe generic 500 RFC 7807 response."""
    logger.exception("Unhandled server exception: %s", exc)
    return create_problem_response(
        status=500,
        title="Internal Server Error",
        detail="An internal server error occurred. Please contact support.",
        instance=request.url.path,
        code="INTERNAL_SERVER_ERROR",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all RFC 7807 error handlers on the FastAPI application."""
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
