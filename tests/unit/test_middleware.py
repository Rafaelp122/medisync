from uuid import uuid4

from src.core.authz.roles import Role
from src.core.config import get_settings
from src.core.middleware import (
    extract_tenant_from_auth_header,
    extract_tenant_from_header,
    extract_tenant_from_host,
)

from tests.unit.test_authz_rbac import create_test_token


def test_extract_tenant_from_header():
    assert extract_tenant_from_header("101") == 101
    assert extract_tenant_from_header("   42   ") == 42
    assert extract_tenant_from_header(None) is None
    assert extract_tenant_from_header("invalid") is None
    assert extract_tenant_from_header("-5") is None
    assert extract_tenant_from_header("0") is None


def test_extract_tenant_from_host():
    assert extract_tenant_from_host("101.medisync.local") == 101
    assert extract_tenant_from_host("tenant-42.medisync.local") == 42
    assert extract_tenant_from_host("101.medisync.local:8000") == 101
    assert extract_tenant_from_host("tenant-42.medisync.local:443") == 42
    assert extract_tenant_from_host("medisync.com.br") is None
    assert extract_tenant_from_host("localhost:8000") is None
    assert extract_tenant_from_host("127.0.0.1:8000") is None
    assert extract_tenant_from_host("192.168.1.100") is None
    assert extract_tenant_from_host("api.medisync.com.br") is None
    assert extract_tenant_from_host(None) is None


def test_extract_tenant_from_auth_header():
    settings = get_settings()
    valid_token = create_test_token(
        usuario_id=uuid4(),
        organizacao_id=77,
        papel=Role.MEDICO,
        secret_key=settings.JWT_SECRET_KEY,
    )

    # Valid Bearer token
    assert extract_tenant_from_auth_header(f"Bearer {valid_token}") == 77
    assert extract_tenant_from_auth_header(f"bearer   {valid_token}  ") == 77

    # Missing / None
    assert extract_tenant_from_auth_header(None) is None
    assert extract_tenant_from_auth_header("") is None

    # Invalid schemes
    assert extract_tenant_from_auth_header(f"Basic {valid_token}") is None
    assert extract_tenant_from_auth_header("InvalidFormat") is None

    # Tampered / invalid token
    assert extract_tenant_from_auth_header("Bearer invalid.token.payload") is None
    bad_secret_token = create_test_token(
        usuario_id=uuid4(),
        organizacao_id=77,
        papel=Role.MEDICO,
        secret_key="wrong_secret_key_1234567890123456",
    )
    assert extract_tenant_from_auth_header(f"Bearer {bad_secret_token}") is None


def test_security_headers_middleware_applies_all_headers():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.core.middleware import SECURITY_HEADERS, SecurityHeadersMiddleware

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/test-headers")
    def sample_endpoint():
        return {"status": "ok"}

    client = TestClient(app)
    response = client.get("/test-headers")

    assert response.status_code == 200
    for header_name, header_value in SECURITY_HEADERS.items():
        assert response.headers.get(header_name.lower()) == header_value


def test_setup_middlewares_includes_security_headers():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.core.middleware import setup_middlewares

    app = FastAPI()
    setup_middlewares(app)

    @app.get("/ping")
    def ping_endpoint():
        return {"ping": "pong"}

    client = TestClient(app)
    response = client.get("/ping")

    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in response.headers.get("content-security-policy", "")
    assert "camera=(self)" in response.headers.get("permissions-policy", "")


def test_security_headers_preserves_custom_headers():
    from fastapi import FastAPI, Response
    from fastapi.testclient import TestClient
    from src.core.middleware import SecurityHeadersMiddleware

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/custom-header")
    def custom_endpoint(response: Response):
        response.headers["x-frame-options"] = "SAMEORIGIN"
        return {"status": "ok"}

    client = TestClient(app)
    response = client.get("/custom-header")
    assert response.status_code == 200
    assert response.headers.get("x-frame-options") == "SAMEORIGIN"
    assert response.headers.get("x-content-type-options") == "nosniff"


def test_security_headers_applied_on_unhandled_error():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.core.middleware import setup_middlewares

    app = FastAPI()
    setup_middlewares(app)

    @app.get("/error")
    def crash_endpoint():
        raise RuntimeError("simulated crash")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/error")

    assert response.status_code == 500
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert "default-src 'self'" in response.headers.get("content-security-policy", "")


def test_security_headers_debug_mode_vs_production_mode():
    from src.core.middleware import get_security_headers

    prod_headers = get_security_headers(debug=False)
    debug_headers = get_security_headers(debug=True)

    prod_csp = prod_headers["Content-Security-Policy"]
    debug_csp = debug_headers["Content-Security-Policy"]

    # Produção: estrito, sem unsafe-inline, sem cdn externo, sem ws: texto claro
    assert "'unsafe-inline'" not in prod_csp
    assert "cdn.jsdelivr.net" not in prod_csp
    assert (
        "ws:" not in prod_csp.split("connect-src")[1]
    )  # garante que ws: não está no connect-src
    assert "wss:" in prod_csp

    # Debug: relaxado para Swagger UI e ws: local
    assert "'unsafe-inline'" in debug_csp
    assert "cdn.jsdelivr.net" in debug_csp
    assert "ws:" in debug_csp
