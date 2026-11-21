"""Integration tests for auth endpoints, anti-enumeration, and Anti-IDOR checks."""

from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.valkey import get_valkey_pool
from src.modules.auth.composition import get_token_service

from tests.factories.auth import persist_credencial
from tests.factories.identity import make_profissional

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_auth_full_lifecycle_login_me_refresh_logout(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate full authentication lifecycle: login, me, token rotation, and logout."""
    medico = make_profissional(
        cpf="11122233344",
        email="dr.lucas@telemed.com.br",
        papel="FATURAMENTO",
        crm="12345",
        crm_uf="SP",
    )
    db_session.add(medico)
    await db_session.commit()
    await db_session.refresh(medico)

    await persist_credencial(
        db_session,
        usuario_id=medico.id,
        identificador=medico.email,
        senha_pura="SenhaForte123!@#",
        papel=medico.papel,
    )

    # 1. Login com credenciais válidas
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={
            "identificador": "dr.lucas@telemed.com.br",
            "senha": "SenhaForte123!@#",
        },
    )
    assert login_resp.status_code == 200
    token_data = cast("dict[str, object]", login_resp.json())
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["expires_in"] == 900

    # Validar atributos de segurança do cookie HttpOnly emitido no login (Issue #144)
    set_cookies = login_resp.headers.get_list("set-cookie")
    cookie_str = next((c for c in set_cookies if "refresh_token=" in c), "")
    assert cookie_str != ""
    assert "httponly" in cookie_str.lower()
    assert "samesite=strict" in cookie_str.lower()
    assert "path=/api/v1/auth" in cookie_str.lower()

    access_token = cast("str", token_data["access_token"])
    refresh_token = cast("str", token_data["refresh_token"])

    # 2. Consultar perfil em /auth/me usando Bearer token
    me_resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200
    me_data = cast("dict[str, object]", me_resp.json())
    assert me_data["usuario_id"] == str(medico.id)
    assert "organizacao_id" not in me_data
    assert me_data["identificador"] == "dr.lucas@telemed.com.br"
    assert me_data["papel"] == "FATURAMENTO"
    assert me_data["ativo"] is True

    # 3. Rotacionar refresh token em /auth/refresh
    refresh_resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 200
    new_token_data = cast("dict[str, object]", refresh_resp.json())
    new_access_token = cast("str", new_token_data["access_token"])
    new_refresh_token = cast("str", new_token_data["refresh_token"])

    assert new_access_token != access_token
    assert new_refresh_token != refresh_token

    # 4. Validar que o refresh token antigo foi invalidado (one-time use rotation)
    stale_refresh_resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert stale_refresh_resp.status_code == 401
    stale_err = cast("dict[str, object]", stale_refresh_resp.json())
    assert stale_err["code"] == "TOKEN_REVOGADO"

    # Validar gravacao no Valkey com chave auth:revoked:{jti}
    # e TTL correspondente ao tempo restante de vida
    valkey_pool = get_valkey_pool()
    valkey_client = Redis(connection_pool=valkey_pool)
    token_service = get_token_service()
    stale_payload = token_service.validar_refresh_token(refresh_token)
    stale_ttl = await valkey_client.ttl(f"auth:revoked:{stale_payload.jti}")
    assert stale_ttl > 0
    assert stale_ttl <= 7 * 86400

    # 5. Logout com o novo refresh token e novo access token
    logout_resp = await async_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": new_refresh_token},
        headers={"Authorization": f"Bearer {new_access_token}"},
    )
    assert logout_resp.status_code == 204
    logout_cookie_str = next(
        (
            c
            for c in logout_resp.headers.get_list("set-cookie")
            if "refresh_token=" in c
        ),
        "",
    )
    assert logout_cookie_str != ""
    assert "max-age=0" in logout_cookie_str.lower()

    # 6. Validar que o refresh token revogado pelo logout nao pode mais ser utilizado
    revoked_refresh_resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh_token},
    )
    assert revoked_refresh_resp.status_code == 401
    revoked_err = cast("dict[str, object]", revoked_refresh_resp.json())
    assert revoked_err["code"] == "TOKEN_REVOGADO"

    # 7. Validar que o access token revogado pelo logout e rejeitado imediatamente
    revoked_access_resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {new_access_token}"},
    )
    assert revoked_access_resp.status_code == 401
    revoked_acc_err = cast("dict[str, object]", revoked_access_resp.json())
    assert revoked_acc_err["code"] == "TOKEN_REVOGADO"


@pytest.mark.asyncio
async def test_auth_anti_enumeration_and_lockout(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate OWASP anti-enumeration and lockout on consecutive failed attempts."""
    medico = make_profissional(
        cpf="22233344455",
        email="dra.juliana@telemed.com.br",
        papel="MEDICO",
        crm="54321",
        crm_uf="RJ",
    )
    db_session.add(medico)
    await db_session.commit()
    await db_session.refresh(medico)

    await persist_credencial(
        db_session,
        usuario_id=medico.id,
        identificador=medico.email,
        senha_pura="SenhaCorreta123!",
        papel=medico.papel,
    )

    # 1. Usuário inexistente retorna 401 genérico
    resp_absent = await async_client.post(
        "/api/v1/auth/login",
        json={
            "identificador": "inexistente@telemed.com.br",
            "senha": "SenhaQualquer123!",
        },
    )
    assert resp_absent.status_code == 401
    err_absent = cast("dict[str, object]", resp_absent.json())
    assert err_absent["title"] == "Credenciais Inválidas"
    assert err_absent["detail"] == "Credenciais de autenticação inválidas."

    # 2. Senha errada: mesma mensagem de erro genérica (anti-enumeração)
    resp_wrong = await async_client.post(
        "/api/v1/auth/login",
        json={
            "identificador": "dra.juliana@telemed.com.br",
            "senha": "SenhaErrada!",
        },
    )
    assert resp_wrong.status_code == 401
    err_wrong = cast("dict[str, object]", resp_wrong.json())
    assert err_wrong["title"] == "Credenciais Inválidas"
    assert err_wrong["detail"] == err_absent["detail"]

    # 3. Forçar 3 falhas adicionais (totalizando 4 falhas consecutivas)
    for _ in range(3):
        r = await async_client.post(
            "/api/v1/auth/login",
            json={
                "identificador": "dra.juliana@telemed.com.br",
                "senha": "SenhaErrada!",
            },
        )
        assert r.status_code == 401

    # 5ª tentativa incorreta deve bloquear a conta (HTTP 423)
    resp_blocked = await async_client.post(
        "/api/v1/auth/login",
        json={
            "identificador": "dra.juliana@telemed.com.br",
            "senha": "SenhaErrada!",
        },
    )
    assert resp_blocked.status_code == 423

    # 6ª tentativa: mesmo com senha correta, rejeitada por bloqueio ativo
    resp_correct_but_blocked = await async_client.post(
        "/api/v1/auth/login",
        json={
            "identificador": "dra.juliana@telemed.com.br",
            "senha": "SenhaCorreta123!",
        },
    )
    assert resp_correct_but_blocked.status_code == 423


@pytest.mark.asyncio
async def test_auth_me_sem_bearer_retorna_401(
    async_client: AsyncClient,
) -> None:
    """Bearer ausente em /auth/me deve retornar 401 (travamento item 5.2)."""
    resp = await async_client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_bearer_malformado_retorna_401(
    async_client: AsyncClient,
) -> None:
    """Bearer malformado em /auth/me deve retornar 401 (travamento item 5.2)."""
    resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Token abc"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bearer_token_accesses_protected_routes_without_tenant_headers(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Verify protected routes rely exclusively on Bearer authentication and RBAC."""
    faturamento = make_profissional(
        cpf="11122233390",
        email="dr.single@telemed.com.br",
        papel="FATURAMENTO",
        crm="12390",
        crm_uf="SP",
    )
    db_session.add(faturamento)
    await db_session.commit()
    await db_session.refresh(faturamento)

    await persist_credencial(
        db_session,
        usuario_id=faturamento.id,
        identificador=faturamento.email,
        senha_pura="SenhaForte123!@#",
        papel=faturamento.papel,
    )

    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={
            "identificador": "dr.single@telemed.com.br",
            "senha": "SenhaForte123!@#",
        },
    )
    assert login_resp.status_code == 200
    access_token = cast("str", login_resp.json()["access_token"])

    me_resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["usuario_id"] == str(faturamento.id)

    # Role FATURAMENTO cannot access patient dependents endpoint (403 RBAC)
    pac_resp = await async_client.get(
        f"/api/v1/pacientes/{uuid4()}/dependentes",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert pac_resp.status_code == 403


@pytest.mark.asyncio
async def test_auth_cookie_lifecycle_and_missing_token_rejection(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate AC-01 to AC-03: Cookie-only refresh,
    missing token 401, and logout purge.
    """
    medico = make_profissional(
        cpf="11122233399",
        email="dr.cookie@telemed.com.br",
        papel="FATURAMENTO",
        crm="12399",
        crm_uf="SP",
    )
    db_session.add(medico)
    await db_session.commit()
    await db_session.refresh(medico)

    await persist_credencial(
        db_session,
        usuario_id=medico.id,
        identificador=medico.email,
        senha_pura="SenhaForte123!@#",
        papel=medico.papel,
    )

    # 1. Requisicao a /refresh sem cookie e sem body deve falhar com 401 TOKEN_INVALIDO
    async_client.cookies.clear()
    empty_refresh_resp = await async_client.post("/api/v1/auth/refresh", json={})
    assert empty_refresh_resp.status_code == 401
    err_data = cast("dict[str, object]", empty_refresh_resp.json())
    assert err_data["code"] == "TOKEN_INVALIDO"

    # 2. Login com emissao de cookie HttpOnly
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={
            "identificador": "dr.cookie@telemed.com.br",
            "senha": "SenhaForte123!@#",
        },
    )
    assert login_resp.status_code == 200
    set_cookie_header = login_resp.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie_header
    assert "httponly" in set_cookie_header.lower()
    assert "samesite=strict" in set_cookie_header.lower()
    assert "path=/api/v1/auth" in set_cookie_header.lower()

    # 3. Silent refresh usando EXCLUSIVAMENTE o cookie no jar (body vazio)
    cookie_refresh_resp = await async_client.post("/api/v1/auth/refresh", json={})
    assert cookie_refresh_resp.status_code == 200
    cookie_refresh_data = cast("dict[str, object]", cookie_refresh_resp.json())
    assert "access_token" in cookie_refresh_data
    # Novo cookie foi rotacionado
    new_set_cookie = cookie_refresh_resp.headers.get("set-cookie", "")
    assert "refresh_token=" in new_set_cookie

    # 4. Logout usando o cookie do jar (sem refresh_token no body)
    logout_resp = await async_client.post("/api/v1/auth/logout", json={})
    assert logout_resp.status_code == 204
    logout_cookie = logout_resp.headers.get("set-cookie", "")
    assert "max-age=0" in logout_cookie.lower()

    # 5. Tentativa de refresh subsequente com cookie revogado/purgado
    revoked_resp = await async_client.post("/api/v1/auth/refresh", json={})
    assert revoked_resp.status_code == 401
