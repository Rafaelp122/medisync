"""HTTP Middlewares: Request ID, Tenant Resolution and Structured Access Logging."""

import ipaddress
import logging
import re
import time
from typing import Any

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)

from src.core.context import (
    reset_current_request_id,
    reset_current_tenant_id,
    set_current_request_id,
    set_current_tenant_id,
)
from src.core.uuid7 import is_valid_uuid, uuid7_str

logger = logging.getLogger("medisync.access")

REQUEST_ID_HEADER = "X-Request-ID"
TENANT_ID_HEADER = "X-Tenant-ID"

_SUBDOMAIN_TENANT_REGEX = re.compile(r"^(?:tenant-)?(\d+)(?:\.|$)", re.IGNORECASE)


def extract_tenant_from_header(header_val: str | None) -> int | None:
    """Extract integer tenant ID from X-Tenant-ID header if present and positive."""
    if not header_val:
        return None
    val_clean = header_val.strip()
    if val_clean.isdigit():
        t = int(val_clean)
        return t if t > 0 else None
    return None


def extract_tenant_from_host(host_val: str | None) -> int | None:
    """Extract integer tenant ID from host subdomain (e.g. 101.domain.com)."""
    if not host_val:
        return None
    # Strip port if present
    host_only = host_val.split(":")[0].strip()
    if host_only == "localhost":
        return None
    try:
        ipaddress.ip_address(host_only)
        return None
    except ValueError:
        pass

    match = _SUBDOMAIN_TENANT_REGEX.match(host_only)
    if match:
        t = int(match.group(1))
        return t if t > 0 else None
    return None


def extract_tenant_from_auth_header(header_val: str | None) -> int | None:
    """Extract integer tenant ID from JWT Bearer token claims if present and valid."""
    if not header_val:
        return None
    parts = header_val.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    raw_token = parts[1]
    try:
        from src.core.authz.token import decode_access_token

        user = decode_access_token(raw_token)
        return user.organizacao_id
    except Exception:
        return None


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Binds a valid UUIDv7 X-Request-ID to contextvars and response."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        incoming_id = request.headers.get(REQUEST_ID_HEADER)
        if incoming_id and is_valid_uuid(incoming_id):
            req_id = incoming_id
        else:
            req_id = uuid7_str()

        token = set_current_request_id(req_id)
        request.state.request_id = req_id

        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                from src.core.errors import unhandled_exception_handler

                response = await unhandled_exception_handler(request, exc)

            response.headers[REQUEST_ID_HEADER] = req_id
            return response
        finally:
            reset_current_request_id(token)


class TenantResolutionMiddleware(BaseHTTPMiddleware):
    """Resolves active tenant ID from header or subdomain and binds to ContextVar."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # 1. Prefer explicit X-Tenant-ID header
        tenant_id = extract_tenant_from_header(request.headers.get(TENANT_ID_HEADER))

        # 2. Fallback to Authorization: Bearer <token> claims
        if tenant_id is None:
            tenant_id = extract_tenant_from_auth_header(
                request.headers.get("Authorization")
            )

        # 3. Fallback to subdomain extraction
        if tenant_id is None:
            tenant_id = extract_tenant_from_host(request.headers.get("host"))

        token = set_current_tenant_id(tenant_id)
        request.state.tenant_id = tenant_id

        try:
            return await call_next(request)
        finally:
            reset_current_tenant_id(token)


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Emits structured JSON access log for each request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start_time = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            client_ip = request.client.host if request.client else "unknown"

            log_extra: dict[str, Any] = {
                "http_method": request.method,
                "http_path": request.url.path,
                "http_status": status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
            }

            msg = f"{request.method} {request.url.path} {status_code} ({duration_ms}ms)"
            logger.info(msg, extra={"extra_fields": log_extra})


def setup_middlewares(app: FastAPI) -> None:
    """Setup middlewares in correct execution order (outermost first).

    Execution order on incoming request:
    1. RequestIDMiddleware (generates / binds request_id)
    2. TenantResolutionMiddleware (binds tenant_id)
    3. StructuredLoggingMiddleware (tracks latency & logs)
    """
    # Note: In Starlette, add_middleware prepends, so we add in reverse order of entry
    app.add_middleware(StructuredLoggingMiddleware)
    app.add_middleware(TenantResolutionMiddleware)
    app.add_middleware(RequestIDMiddleware)
