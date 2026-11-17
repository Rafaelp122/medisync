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

    # Produção: estrito, sem unsafe-inline, sem cdn externo, sem ws: texto claro
    assert prod_directives["script-src"] == ["'self'"]
    assert prod_directives["connect-src"] == ["'self'", "wss:", "https:"]

    # Debug: relaxado para Swagger UI e ws: local
    assert debug_directives["script-src"] == [
        "'self'",
        "'unsafe-inline'",
        "https://cdn.jsdelivr.net",
    ]
    assert debug_directives["connect-src"] == ["'self'", "wss:", "ws:", "https:"]


def test_tenant_resolution_multi_tenant_priority_without_fallback() -> None:
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    from src.core.context import get_current_tenant_id
    from src.core.middleware import setup_middlewares

    app = FastAPI()
    setup_middlewares(app, multi_tenancy_enabled=True, default_tenant_id=None)

    @app.get("/tenant-echo")
    def tenant_echo(request: Request) -> dict[str, int | None]:
        return {
            "context": get_current_tenant_id(),
            "state": request.state.tenant_id,
        }

    settings = get_settings()
    jwt_token = create_test_token(
        usuario_id=uuid4(),
        organizacao_id=77,
        papel=Role.MEDICO,
        secret_key=settings.JWT_SECRET_KEY,
    )
    client = TestClient(app)

    # Sem header/JWT/subdomínio -> None (zero fallback silencioso)
    r_none = client.get("/tenant-echo", headers={"host": "medisync.app"})
    assert r_none.status_code == 200
    assert r_none.json() == {"context": None, "state": None}

    # Subdomínio
    r_sub = client.get("/tenant-echo", headers={"host": "101.medisync.local"})
    assert r_sub.json() == {"context": 101, "state": 101}

    # JWT prevalece sobre subdomínio
    r_jwt = client.get(
        "/tenant-echo",
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "host": "101.medisync.local",
        },
    )
    assert r_jwt.json() == {"context": 77, "state": 77}

    # X-Tenant-ID prevalece sobre JWT e subdomínio
    r_hdr = client.get(
        "/tenant-echo",
        headers={
            "X-Tenant-ID": "55",
            "Authorization": f"Bearer {jwt_token}",
            "host": "101.medisync.local",
        },
    )
    assert r_hdr.json() == {"context": 55, "state": 55}


def test_tenant_resolution_single_tenant_anti_spoofing() -> None:
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    from src.core.context import get_current_tenant_id
    from src.core.middleware import setup_middlewares

    app = FastAPI()
    setup_middlewares(app, multi_tenancy_enabled=False, default_tenant_id=7)

    @app.get("/tenant-echo")
    def tenant_echo(request: Request) -> dict[str, int | None]:
        return {
            "context": get_current_tenant_id(),
            "state": request.state.tenant_id,
        }

    settings = get_settings()
    spoofed_jwt = create_test_token(
        usuario_id=uuid4(),
        organizacao_id=88,
        papel=Role.MEDICO,
        secret_key=settings.JWT_SECRET_KEY,
    )
    client = TestClient(app)

    # Sem headers -> vincula default_tenant_id=7
    assert client.get("/tenant-echo").json() == {"context": 7, "state": 7}

    # Tentativa de spoofing via X-Tenant-ID, JWT e subdomínio -> sempre 7
    resp = client.get(
        "/tenant-echo",
        headers={
            "X-Tenant-ID": "999",
            "Authorization": f"Bearer {spoofed_jwt}",
            "host": "101.medisync.local",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"context": 7, "state": 7}


def test_tenant_resolution_middleware_single_tenant_requires_valid_default() -> None:
    import pytest
    from fastapi import FastAPI
    from src.core.middleware import TenantResolutionMiddleware

    app = FastAPI()
    for invalid in (None, 0, -3):
        with pytest.raises(ValueError, match="default_tenant_id="):
            TenantResolutionMiddleware(
                app,
                multi_tenancy_enabled=False,
                default_tenant_id=invalid,
            )


def test_resolve_login_tenant_id_single_tenant_anti_spoofing() -> None:
    import pytest
    from src.core.errors import ValidationError
    from src.modules.auth.presentation.helpers import resolve_login_tenant_id

    assert (
        resolve_login_tenant_id(
            999,
            1,
            multi_tenancy_enabled=False,
            default_tenant_id=7,
        )
        == 7
    )
    assert (
        resolve_login_tenant_id(
            None,
            None,
            multi_tenancy_enabled=False,
            default_tenant_id=7,
        )
        == 7
    )
    with pytest.raises(ValidationError, match="DEFAULT_TENANT_ID"):
        resolve_login_tenant_id(
            999,
            888,
            multi_tenancy_enabled=False,
            default_tenant_id=None,
        )


def test_livekit_token_request_accepts_optional_organizacao_id() -> None:
    from src.modules.consultation.presentation.schemas import LiveKitTokenRequest

    req = LiveKitTokenRequest(participant_id=uuid4(), role="paciente")
    assert req.organizacao_id is None


def test_livekit_router_resolves_tenant_when_organizacao_id_omitted() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.core.authz.roles import Role as AuthRole
    from src.core.errors import register_exception_handlers
    from src.core.middleware import setup_middlewares
    from src.modules.consultation.application.ports.atendimento_reader_port import (
        AtendimentoResumoDTO,
    )
    from src.modules.consultation.composition import get_atendimento_reader
    from src.modules.consultation.presentation.routers.livekit_router import (
        livekit_router,
    )

    from tests.doubles import FakeAtendimentoReader

    atend_id = uuid4()
    doctor_id = uuid4()
    org_id = 7
    reader = FakeAtendimentoReader(
        AtendimentoResumoDTO(
            atendimento_id=atend_id,
            organizacao_id=org_id,
            medico_id=doctor_id,
            paciente_id=uuid4(),
            status="EM_ATENDIMENTO",
            tcle_hash="a" * 64,
            is_terminal=False,
        )
    )

    app = FastAPI()
    register_exception_handlers(app)
    setup_middlewares(app, multi_tenancy_enabled=False, default_tenant_id=org_id)
    app.include_router(livekit_router, prefix="/api/v1")
    app.dependency_overrides[get_atendimento_reader] = lambda: reader

    settings = get_settings()
    token = create_test_token(
        usuario_id=doctor_id,
        organizacao_id=org_id,
        papel=AuthRole.MEDICO,
        secret_key=settings.JWT_SECRET_KEY,
    )
    client = TestClient(app)

    # Sem organizacao_id no payload -> resolve via context_tenant_id (7)
    resp = client.post(
        f"/api/v1/consultations/{atend_id}/livekit/token",
        json={"participant_id": str(doctor_id), "role": "medico"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["room_name"] == f"org_{org_id}_atend_{atend_id}"

    # Com organizacao_id divergente -> 403 Forbidden
    resp_div = client.post(
        f"/api/v1/consultations/{atend_id}/livekit/token",
        json={
            "organizacao_id": 999,
            "participant_id": str(doctor_id),
            "role": "medico",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_div.status_code == 403


def test_livekit_router_multi_tenant_rejects_missing_tenant_when_omitted() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.core.config import get_settings as _get_settings
    from src.core.errors import register_exception_handlers
    from src.core.middleware import setup_middlewares
    from src.core.security import create_intake_token
    from src.modules.consultation.application.ports.atendimento_reader_port import (
        AtendimentoResumoDTO,
    )
    from src.modules.consultation.composition import get_atendimento_reader
    from src.modules.consultation.presentation.routers.livekit_router import (
        livekit_router,
    )

    from tests.doubles import FakeAtendimentoReader

    atend_id = uuid4()
    patient_id = uuid4()
    org_id = 7
    reader = FakeAtendimentoReader(
        AtendimentoResumoDTO(
            atendimento_id=atend_id,
            organizacao_id=org_id,
            medico_id=uuid4(),
            paciente_id=patient_id,
            status="CHAMANDO_PACIENTE",
            tcle_hash="a" * 64,
            is_terminal=False,
        )
    )

    app = FastAPI()
    register_exception_handlers(app)
    setup_middlewares(app, multi_tenancy_enabled=True, default_tenant_id=None)
    app.include_router(livekit_router, prefix="/api/v1")
    app.dependency_overrides[get_atendimento_reader] = lambda: reader

    intake_token = create_intake_token(patient_id, org_id, _get_settings().SECRET_KEY)
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/consultations/{atend_id}/livekit/token",
        json={"participant_id": str(patient_id), "role": "paciente"},
        headers={"Authorization": f"Bearer {intake_token}"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "TENANT_INVALIDO"
