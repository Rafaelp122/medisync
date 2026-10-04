from collections.abc import AsyncGenerator
from typing import Any, cast

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from src.core.database import async_session_factory
from src.core.valkey import get_valkey_pool
from src.main import app
from src.modules.auth.application.dtos import CadastrarCredencialCommand
from src.modules.auth.application.services.auth_service import AuthService

from tests.factories.identity import make_organizacao, make_profissional


@pytest.fixture(autouse=True)
async def setup_auth_db() -> AsyncGenerator[None, None]:
    """Ensure database schema is ready and Valkey rate limit keys are clean."""
    pool = get_valkey_pool()
    client = Redis(connection_pool=pool)
    valkey_any = cast("Any", client)
    keys_before = cast("list[str]", await valkey_any.keys("auth:ratelimit:*"))
    if keys_before:
        await valkey_any.delete(*keys_before)

    from tests.helpers import clean_database_tables

    await clean_database_tables()
    yield
    keys_after = cast("list[str]", await valkey_any.keys("auth:ratelimit:*"))
    if keys_after:
        await valkey_any.delete(*keys_after)

    await clean_database_tables()


@pytest.mark.asyncio
async def test_auth_full_lifecycle_login_me_refresh_logout() -> None:
    """Validate full authentication lifecycle: login, me, token rotation, and logout."""
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="88777666000155")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        medico = make_profissional(
            org.id,
            cpf="11122233344",
            email="dr.lucas@telemed.com.br",
            papel="MEDICO",
            crm="12345",
            crm_uf="SP",
        )
        session.add(medico)
        await session.commit()
        await session.refresh(medico)

        # Cadastrar credencial via AuthService
        service = AuthService(session)
        await service.cadastrar_credencial(
            CadastrarCredencialCommand(
                organizacao_id=org.id,
                usuario_id=medico.id,
                identificador=medico.email,
                senha_pura="SenhaForte123!@#",
                papel=medico.papel,
            )
        )
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Tenant-ID": str(org.id)},
    ) as client:
        # 1. Login com credenciais válidas
        login_resp = await client.post(
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

        access_token = cast("str", token_data["access_token"])
        refresh_token = cast("str", token_data["refresh_token"])

        # 2. Consultar perfil em /auth/me usando Bearer token
        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_resp.status_code == 200
        me_data = cast("dict[str, object]", me_resp.json())
        assert me_data["usuario_id"] == str(medico.id)
        assert me_data["organizacao_id"] == org.id
        assert me_data["identificador"] == "dr.lucas@telemed.com.br"
        assert me_data["papel"] == "MEDICO"
        assert me_data["ativo"] is True

        # 3. Rotacionar refresh token em /auth/refresh
        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_resp.status_code == 200
        new_token_data = cast("dict[str, object]", refresh_resp.json())
        new_access_token = cast("str", new_token_data["access_token"])
        new_refresh_token = cast("str", new_token_data["refresh_token"])

        assert new_access_token != access_token
        assert new_refresh_token != refresh_token

        # 4. Validar que o refresh token antigo foi invalidado (one-time use)
        stale_refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert stale_refresh_resp.status_code == 401

        # 5. Logout com o novo refresh token
        logout_resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": new_refresh_token},
        )
        assert logout_resp.status_code == 204

        # 6. Validar que o token revogado pelo logout não pode mais ser utilizado
        revoked_refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": new_refresh_token},
        )
        assert revoked_refresh_resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_anti_enumeration_and_lockout() -> None:
    """Validate OWASP anti-enumeration and lockout on consecutive failed attempts."""
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="88777666000156")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        medico = make_profissional(
            org.id,
            cpf="22233344455",
            email="dra.juliana@telemed.com.br",
            papel="MEDICO",
            crm="54321",
            crm_uf="RJ",
        )
        session.add(medico)
        await session.commit()
        await session.refresh(medico)

        service = AuthService(session)
        await service.cadastrar_credencial(
            CadastrarCredencialCommand(
                organizacao_id=org.id,
                usuario_id=medico.id,
                identificador=medico.email,
                senha_pura="SenhaCorreta123!",
                papel=medico.papel,
            )
        )
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Tenant-ID": str(org.id)},
    ) as client:
        # 1. Usuário inexistente retorna 401 genérico
        resp_absent = await client.post(
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
        resp_wrong = await client.post(
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
            r = await client.post(
                "/api/v1/auth/login",
                json={
                    "identificador": "dra.juliana@telemed.com.br",
                    "senha": "SenhaErrada!",
                },
            )
            assert r.status_code == 401

        # 5ª tentativa incorreta deve bloquear a conta (HTTP 423)
        resp_blocked = await client.post(
            "/api/v1/auth/login",
            json={
                "identificador": "dra.juliana@telemed.com.br",
                "senha": "SenhaErrada!",
            },
        )
        assert resp_blocked.status_code == 423

        # 6ª tentativa: mesmo com senha correta, rejeitada por bloqueio ativo
        resp_correct_but_blocked = await client.post(
            "/api/v1/auth/login",
            json={
                "identificador": "dra.juliana@telemed.com.br",
                "senha": "SenhaCorreta123!",
            },
        )
        assert resp_correct_but_blocked.status_code == 423


@pytest.mark.asyncio
async def test_auth_cross_tenant_isolation() -> None:
    """Validate cross-tenant credential isolation rejects login with 401."""
    async with async_session_factory() as session:
        org_a = make_organizacao(cnpj="88777666000157")
        org_b = make_organizacao(cnpj="88777666000158")
        session.add_all([org_a, org_b])
        await session.commit()
        await session.refresh(org_a)
        await session.refresh(org_b)

        medico_a = make_profissional(
            org_a.id,
            cpf="33344455566",
            email="dr.tenant_a@telemed.com.br",
            papel="MEDICO",
            crm="11223",
            crm_uf="MG",
        )
        session.add(medico_a)
        await session.commit()
        await session.refresh(medico_a)

        service = AuthService(session)
        await service.cadastrar_credencial(
            CadastrarCredencialCommand(
                organizacao_id=org_a.id,
                usuario_id=medico_a.id,
                identificador=medico_a.email,
                senha_pura="SenhaOrgA123!",
                papel=medico_a.papel,
            )
        )
        await session.commit()

    transport = ASGITransport(app=app)
    # Tentar logar usando o cabeçalho do Tenant B com as credenciais do Tenant A
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Tenant-ID": str(org_b.id)},
    ) as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={
                "identificador": "dr.tenant_a@telemed.com.br",
                "senha": "SenhaOrgA123!",
            },
        )
        # Deve falhar com 401 por isolamento de tenant
        assert resp.status_code == 401
