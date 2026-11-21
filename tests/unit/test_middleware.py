"""Unit tests for HTTP security headers, request ID, and logging middlewares."""

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from src.core import middleware as core_middleware
from src.core.middleware import (
    SECURITY_HEADERS,
    SecurityHeadersMiddleware,
    get_security_headers,
    setup_middlewares,
)


def test_security_headers_middleware_applies_all_headers() -> None:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/test-headers")
    def sample_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(app)
    response = client.get("/test-headers")

    assert response.status_code == 200
    for header_name, header_value in SECURITY_HEADERS.items():
        assert response.headers.get(header_name.lower()) == header_value


def test_setup_middlewares_includes_security_headers() -> None:
    app = FastAPI()
    setup_middlewares(app)

    @app.get("/ping")
    def ping_endpoint() -> dict[str, str]:
        return {"ping": "pong"}

    client = TestClient(app)
    response = client.get("/ping")

    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in response.headers.get("content-security-policy", "")
    assert "camera=(self)" in response.headers.get("permissions-policy", "")


def test_security_headers_preserves_custom_headers() -> None:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/custom-header")
    def custom_endpoint(response: Response) -> dict[str, str]:
        response.headers["x-frame-options"] = "SAMEORIGIN"
        return {"status": "ok"}

    client = TestClient(app)
    response = client.get("/custom-header")
    assert response.status_code == 200
    assert response.headers.get("x-frame-options") == "SAMEORIGIN"
    assert response.headers.get("x-content-type-options") == "nosniff"


def test_security_headers_applied_on_unhandled_error() -> None:
    app = FastAPI()
    setup_middlewares(app)

    @app.get("/error")
    def crash_endpoint() -> None:
        raise RuntimeError("simulated crash")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/error")

    assert response.status_code == 500
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert "default-src 'self'" in response.headers.get("content-security-policy", "")


def test_security_headers_debug_mode_vs_production_mode() -> None:
    prod_headers = get_security_headers(debug=False)
    debug_headers = get_security_headers(debug=True)

    prod_directives: dict[str, list[str]] = {
        parts[0]: parts[1:]
        for item in prod_headers["Content-Security-Policy"].split(";")
        if (parts := item.strip().split())
    }
    debug_directives: dict[str, list[str]] = {
        parts[0]: parts[1:]
        for item in debug_headers["Content-Security-Policy"].split(";")
        if (parts := item.strip().split())
    }

    assert prod_directives["script-src"] == ["'self'"]
    assert prod_directives["connect-src"] == ["'self'", "wss:", "https:"]
    assert debug_directives["script-src"] == [
        "'self'",
        "'unsafe-inline'",
        "https://cdn.jsdelivr.net",
    ]
    assert debug_directives["connect-src"] == ["'self'", "wss:", "ws:", "https:"]


def test_middleware_pipeline_sem_tenant_resolution() -> None:
    """Middleware pipeline works without TenantResolutionMiddleware or X-Tenant-ID."""
    assert not hasattr(core_middleware, "TenantResolutionMiddleware")
    assert not hasattr(core_middleware, "TENANT_ID_HEADER")
    assert not hasattr(core_middleware, "extract_tenant_from_header")
    assert not hasattr(core_middleware, "extract_tenant_from_host")
    assert not hasattr(core_middleware, "extract_tenant_from_auth_header")

    app = FastAPI()
    setup_middlewares(app)

    @app.get("/status")
    def status_endpoint(request: Request) -> dict[str, object]:
        return {
            "request_id": request.state.request_id,
            "has_tenant_state": hasattr(request.state, "tenant_id"),
        }

    client = TestClient(app)
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["request_id"]
    assert data["has_tenant_state"] is False
    assert resp.headers.get("x-request-id") == data["request_id"]
