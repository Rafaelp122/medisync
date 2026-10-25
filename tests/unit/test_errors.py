from typing import TYPE_CHECKING

import pytest
from src.core.errors import (
    BadRequestError,
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    ProblemDetails,
    UnauthorizedError,
    ValidationError,
)

if TYPE_CHECKING:
    from starlette.types import Scope


def test_problem_details_model():
    p = ProblemDetails(
        type="https://errors.medisync.com/not-found",
        title="Not Found",
        status=404,
        detail="Patient not found",
        instance="/api/v1/patients/123",
        request_id="req-123",
    )
    d = p.model_dump(exclude_none=True)
    assert d["status"] == 404
    assert d["title"] == "Not Found"
    assert d["detail"] == "Patient not found"
    assert d["request_id"] == "req-123"


def test_domain_error_hierarchy():
    err = NotFoundError("Patient not found")
    assert isinstance(err, DomainError)
    assert err.status_code == 404
    assert err.title == "Not Found"
    assert err.detail == "Patient not found"

    err_conflict = ConflictError("Resource already locked")
    assert err_conflict.status_code == 409
    assert err_conflict.title == "Conflict"

    err_unauth = UnauthorizedError("Missing token")
    assert err_unauth.status_code == 401

    err_forbidden = ForbiddenError("Access denied")
    assert err_forbidden.status_code == 403

    err_bad = BadRequestError("Invalid parameter")
    assert err_bad.status_code == 400

    err_val = ValidationError("Invalid payload")
    assert err_val.status_code == 422


def test_domain_error_custom_attributes():
    err = DomainError(
        "Custom error occurred",
        status_code=418,
        title="I'm a teapot",
        error_type="https://errors.medisync.com/teapot",
        code="TEAPOT_ERROR",
    )
    assert err.status_code == 418
    assert err.title == "I'm a teapot"
    assert err.error_type == "https://errors.medisync.com/teapot"
    assert err.code == "TEAPOT_ERROR"


@pytest.mark.asyncio
async def test_http_exception_handler_uses_http_status_phrase_and_name() -> None:
    import json

    from src.core.errors import http_exception_handler
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from starlette.requests import Request

    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/test-endpoint",
        "headers": [],
    }
    req = Request(scope)
    exc = StarletteHTTPException(status_code=404, detail="Resource not found")
    resp = await http_exception_handler(req, exc)
    assert resp.status_code == 404
    data = json.loads(bytes(resp.body).decode("utf-8"))
    assert data["status"] == 404
    assert data["title"] == "Not Found"
    assert data["code"] == "NOT_FOUND"
    assert data["detail"] == "Resource not found"


@pytest.mark.asyncio
async def test_http_exception_handler_rate_limit_429() -> None:
    import json

    from src.core.errors import http_exception_handler
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from starlette.requests import Request

    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth",
        "headers": [],
    }
    req = Request(scope)
    exc = StarletteHTTPException(status_code=429, detail="Too many attempts")
    resp = await http_exception_handler(req, exc)
    assert resp.status_code == 429
    data = json.loads(bytes(resp.body).decode("utf-8"))
    assert data["title"] == "Too Many Requests"
    assert data["code"] == "TOO_MANY_REQUESTS"


@pytest.mark.asyncio
async def test_domain_error_handler_repassa_headers_retry_after() -> None:
    import json

    from src.core.errors import DomainError, domain_error_handler
    from starlette.requests import Request

    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/patient/otp/verify",
        "headers": [],
    }
    req = Request(scope)
    exc = DomainError(
        "Tentativas excedidas.",
        status_code=429,
        title="Tentativas de OTP Excedidas",
        code="OTP_TENTATIVAS_EXCEDIDAS",
        headers={"Retry-After": "900"},
    )
    resp = await domain_error_handler(req, exc)
    assert resp.status_code == 429
    assert resp.headers.get("retry-after") == "900"
    data = json.loads(bytes(resp.body).decode("utf-8"))
    assert data["status"] == 429
    assert data["title"] == "Tentativas de OTP Excedidas"
    assert data["code"] == "OTP_TENTATIVAS_EXCEDIDAS"
    assert data["detail"] == "Tentativas excedidas."
