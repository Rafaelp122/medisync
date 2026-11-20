"""HTTP Middlewares: Request ID, Security Headers and Structured Access Logging."""

import logging
import time
from typing import Any

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.types import ASGIApp

from src.core.logging import reset_current_request_id, set_current_request_id
from src.core.telemetry import get_current_trace_context
from src.core.uuid7 import is_valid_uuid, uuid7_str

logger = logging.getLogger("medisync.access")

REQUEST_ID_HEADER = "X-Request-ID"


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

            trace_id, span_id = get_current_trace_context()
            if trace_id is not None:
                log_extra["trace_id"] = trace_id
            if span_id is not None:
                log_extra["span_id"] = span_id

            msg = f"{request.method} {request.url.path} {status_code} ({duration_ms}ms)"
            logger.info(msg, extra={"extra_fields": log_extra})


def get_security_headers(debug: bool = False) -> dict[str, str]:
    """Gera mapa de cabeçalhos HTTP estritos de proteção de borda.

    Regras: docs/explanation/architecture/security-and-authorization.md §6.1,
    OWASP ASVS v4.0 e ADR-010.
    """
    script_src = (
        "'self' 'unsafe-inline' https://cdn.jsdelivr.net" if debug else "'self'"
    )
    style_src = "'self' 'unsafe-inline' https://cdn.jsdelivr.net" if debug else "'self'"
    connect_src = "'self' wss: ws: https:" if debug else "'self' wss: https:"

    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(self), microphone=(self), geolocation=()",
        "Content-Security-Policy": (
            "default-src 'self'; "
            f"script-src {script_src}; "
            f"style-src {style_src}; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            f"connect-src {connect_src}; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "base-uri 'self'"
        ),
    }


SECURITY_HEADERS: dict[str, str] = get_security_headers(debug=False)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injeta cabeçalhos HTTP de segurança estrita em todas as respostas da API.

    Regras: docs/explanation/architecture/security-and-authorization.md §6.1,
    OWASP ASVS v4.0 e ADR-010.
    """

    def __init__(self, app: ASGIApp, debug: bool = False) -> None:
        super().__init__(app)
        self.headers = get_security_headers(debug=debug)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        for header_name, header_value in self.headers.items():
            response.headers.setdefault(header_name, header_value)
        return response


def setup_middlewares(app: FastAPI, debug: bool = False) -> None:
    """Setup middlewares in correct execution order (outermost first).

    Execution order on incoming request:
    1. SecurityHeadersMiddleware (applies security headers to all responses)
    2. RequestIDMiddleware (generates / binds request_id)
    3. StructuredLoggingMiddleware (tracks latency & logs)
    """
    # Note: In Starlette, add_middleware prepends, so we add in reverse order of entry
    app.add_middleware(StructuredLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, debug=debug)
