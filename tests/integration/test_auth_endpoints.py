"""Integration tests for auth endpoints, anti-enumeration, and tenant isolation."""

from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories.auth import persist_credencial
from tests.factories.identity import make_organizacao, make_profissional
from tests.factories.scenarios import seed_multi_tenant_orgs

pytestmark = pytest.mark.usefixtures("clean_db_and_valkey")


@pytest.mark.asyncio
async def test_auth_full_lifecycle_login_me_refresh_logout(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate full authentication lifecycle: login, me, token rotation, and logout."""
    org = make_organizacao(cnpj="88777666000155")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    medico = make_profissional(
        org.id,
        cpf="11122233344",
        email="dr.lucas@telemed.com.br",
        papel="MEDICO",
        crm="12345",
        crm_uf="SP",
    )
    db_session.add(medico)
    await db_session.commit()
    await db_session.refresh(medico)

    await persist_credencial(
        db_session,
        organizacao_id=org.id,
        usuario_id=medico.id,
        identificador=medico.email,
        senha_pura="SenhaForte123!@#",
        papel=medico.papel,
    )

    headers = {"X-Tenant-ID": str(org.id)}

    # 1. Login com credenciais válidas
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={
            "identificador": "dr.lucas@telemed.com.br",
            "senha": "SenhaForte123!@#",
        },
        headers=headers,
    )
    assert login_resp.status_code == 200
    token_data = cast("dict[str, object]", login_resp.json())
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["expires_in"] == 900

    access_token = cast("str", token_data["access_token"])
    refresh_token = cast("str", token_data["refresh_token"])

    # 2. Consultar perfil em /auth/me usando Bearer token
    me_resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}", **headers},
    )
    assert me_resp.status_code == 200
    me_data = cast("dict[str, object]", me_resp.json())
    assert me_data["usuario_id"] == str(medico.id)
    assert me_data["organizacao_id"] == org.id
    assert me_data["identificador"] == "dr.lucas@telemed.com.br"
    assert me_data["papel"] == "MEDICO"
    assert me_data["ativo"] is True

    # 3. Rotacionar refresh token em /auth/refresh
    refresh_resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
        headers=headers,
    )
    assert refresh_resp.status_code == 200
    new_token_data = cast("dict[str, object]", refresh_resp.json())
    new_access_token = cast("str", new_token_data["access_token"])
    new_refresh_token = cast("str", new_token_data["refresh_token"])

    assert new_access_token != access_token
    assert new_refresh_token != refresh_token

    # 4. Validar que o refresh token antigo foi invalidado (one-time use)
    stale_refresh_resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
        headers=headers,
    )
    assert stale_refresh_resp.status_code == 401

    # 5. Logout com o novo refresh token
    logout_resp = await async_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": new_refresh_token},
        headers=headers,
    )
    assert logout_resp.status_code == 204

    # 6. Validar que o token revogado pelo logout não pode mais ser utilizado
    revoked_refresh_resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh_token},
        headers=headers,
    )
    assert revoked_refresh_resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_anti_enumeration_and_lockout(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate OWASP anti-enumeration and lockout on consecutive failed attempts."""
    org = make_organizacao(cnpj="88777666000156")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    medico = make_profissional(
        org.id,
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
        organizacao_id=org.id,
        usuario_id=medico.id,
        identificador=medico.email,
        senha_pura="SenhaCorreta123!",
        papel=medico.papel,
    )

    headers = {"X-Tenant-ID": str(org.id)}

    # 1. Usuário inexistente retorna 401 genérico
    resp_absent = await async_client.post(
        "/api/v1/auth/login",
        json={
            "identificador": "inexistente@telemed.com.br",
            "senha": "SenhaQualquer123!",
        },
        headers=headers,
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
        headers=headers,
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
            headers=headers,
        )
        assert r.status_code == 401

    # 5ª tentativa incorreta deve bloquear a conta (HTTP 423)
    resp_blocked = await async_client.post(
        "/api/v1/auth/login",
        json={
            "identificador": "dra.juliana@telemed.com.br",
            "senha": "SenhaErrada!",
        },
        headers=headers,
    )
    assert resp_blocked.status_code == 423

    # 6ª tentativa: mesmo com senha correta, rejeitada por bloqueio ativo
    resp_correct_but_blocked = await async_client.post(
        "/api/v1/auth/login",
        json={
            "identificador": "dra.juliana@telemed.com.br",
            "senha": "SenhaCorreta123!",
        },
        headers=headers,
    )
    assert resp_correct_but_blocked.status_code == 423


@pytest.mark.asyncio
async def test_auth_cross_tenant_isolation(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate cross-tenant credential isolation rejects login with 401."""
    org_a, org_b = await seed_multi_tenant_orgs(
        db_session,
        cnpj_a="88777666000157",
        cnpj_b="88777666000158",
    )

    medico_a = make_profissional(
        org_a.id,
        cpf="33344455566",
        email="dr.tenant_a@telemed.com.br",
        papel="MEDICO",
        crm="11223",
        crm_uf="MG",
    )
    db_session.add(medico_a)
    await db_session.commit()
    await db_session.refresh(medico_a)

    await persist_credencial(
        db_session,
        organizacao_id=org_a.id,
        usuario_id=medico_a.id,
        identificador=medico_a.email,
        senha_pura="SenhaOrgA123!",
        papel=medico_a.papel,
    )

    # Tentar logar usando o cabeçalho do Tenant B com as credenciais do Tenant A
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={
            "identificador": "dr.tenant_a@telemed.com.br",
            "senha": "SenhaOrgA123!",
        },
        headers={"X-Tenant-ID": str(org_b.id)},
    )
    # Deve falhar com 401 por isolamento de tenant
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_sem_bearer_retorna_401(
    async_client: AsyncClient,
) -> None:
    """Bearer ausente em /auth/me deve retornar 401 (travamento item 5.2)."""
    resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"X-Tenant-ID": "1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_bearer_malformado_retorna_401(
    async_client: AsyncClient,
) -> None:
    """Bearer malformado em /auth/me deve retornar 401 (travamento item 5.2)."""
    resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Token abc", "X-Tenant-ID": "1"},
    )
    assert resp.status_code == 401
