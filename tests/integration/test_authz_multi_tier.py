"""Integration tests for OWASP multi-tier authorization framework.

Enforces Tier 1 RBAC and Tier 3 Clinical ABAC/ReBAC context.
"""

from collections.abc import AsyncGenerator
from typing import cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from src.core.authz.roles import Role
from src.core.config import get_settings
from src.core.database import async_session_factory
from src.main import app
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService

from tests.factories.identity import (
    make_organizacao,
    make_paciente,
    make_profissional,
)
from tests.factories.queue import make_atendimento
from tests.helpers import clean_database_tables


def _create_token(usuario_id: UUID, org_id: int, papel: str) -> str:
    """Helper to generate signed JWT access tokens."""
    token_service = JWTTokenService(secret_key=get_settings().JWT_SECRET_KEY)
    return token_service.gerar_tokens(usuario_id, org_id, papel).access_token


@pytest.fixture(autouse=True)
async def setup_authz_db() -> AsyncGenerator[None, None]:
    """Ensure clean database schema before and after each test."""
    await clean_database_tables()
    yield
    await clean_database_tables()


@pytest.mark.asyncio
async def test_authz_unauthenticated_request_blocked() -> None:
    """Validate requests without Authorization header are rejected with 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        resp = await client.get(f"/consultations/{uuid4()}/prontuario")
        assert resp.status_code == 401
        err = cast("dict[str, object]", resp.json())
        assert err["title"] == "Unauthorized"
        assert "não fornecida" in str(err["detail"])


@pytest.mark.asyncio
async def test_authz_macro_rbac_unauthorized_role_blocked() -> None:
    """Validate Tier 1 Macro RBAC blocks non-medico roles with 403 Problem Details."""
    org_id = 77
    token_gestor = _create_token(uuid4(), org_id, Role.GESTOR_UNIDADE)
    token_faturamento = _create_token(uuid4(), org_id, Role.FATURAMENTO)
    token_paciente = _create_token(uuid4(), org_id, Role.PACIENTE)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Tenant-ID": str(org_id)},
    ) as client:
        atend_id = uuid4()

        # 1. GESTOR_UNIDADE blocked
        resp_g = await client.get(
            f"/consultations/{atend_id}/prontuario",
            headers={"Authorization": f"Bearer {token_gestor}"},
        )
        assert resp_g.status_code == 403
        err_g = cast("dict[str, object]", resp_g.json())
        assert err_g["title"] == "Forbidden"
        assert "GESTOR_UNIDADE" in str(err_g["detail"])

        # 2. FATURAMENTO blocked
        resp_f = await client.get(
            f"/consultations/{atend_id}/prontuario",
            headers={"Authorization": f"Bearer {token_faturamento}"},
        )
        assert resp_f.status_code == 403
        assert "FATURAMENTO" in str(cast("dict[str, object]", resp_f.json())["detail"])

        # 3. PACIENTE blocked
        resp_p = await client.get(
            f"/consultations/{atend_id}/prontuario",
            headers={"Authorization": f"Bearer {token_paciente}"},
        )
        assert resp_p.status_code == 403
        assert "PACIENTE" in str(cast("dict[str, object]", resp_p.json())["detail"])


@pytest.mark.asyncio
async def test_authz_tenant_mismatch_blocked() -> None:
    """Validate cross-tenant token usage is blocked with 403 Problem Details."""
    org_a_id = 81
    org_b_id = 82
    token_medico_org_a = _create_token(uuid4(), org_a_id, Role.MEDICO)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Tenant-ID": str(org_b_id)},  # Requesting Org B with Org A token
    ) as client:
        resp = await client.get(
            f"/consultations/{uuid4()}/prontuario",
            headers={"Authorization": f"Bearer {token_medico_org_a}"},
        )
        assert resp.status_code == 403
        err = cast("dict[str, object]", resp.json())
        assert err["title"] == "Forbidden"
        assert "organização 81" in str(err["detail"])


@pytest.mark.asyncio
async def test_authz_clinical_abac_missing_tcle_blocked() -> None:
    """Validate Tier 3 ABAC blocks access if TCLE is not signed (CFM 2.314/2022)."""
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="77111222000199")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="11122233344")
        medico = make_profissional(
            org.id,
            cpf="22233344499",
            email="dr.fernando@hospital.com",
            papel=Role.MEDICO,
            crm="98765",
            crm_uf="SP",
        )
        session.add_all([paciente, medico])
        await session.commit()
        await session.refresh(paciente)
        await session.refresh(medico)

        # Atendimento sem TCLE assinado (tcle_hash=None)
        atendimento = make_atendimento(
            organizacao_id=org.id,
            paciente_id=paciente.id,
            medico_id=medico.id,
            status="EM_ATENDIMENTO",
            tcle_hash=None,
        )
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

    token_medico = _create_token(medico.id, org.id, Role.MEDICO)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Tenant-ID": str(org.id)},
    ) as client:
        resp = await client.get(
            f"/consultations/{atendimento.id}/prontuario",
            headers={"Authorization": f"Bearer {token_medico}"},
        )
        assert resp.status_code == 403
        err = cast("dict[str, object]", resp.json())
        assert err["title"] == "Forbidden"
        assert "TCLE" in str(err["detail"])


@pytest.mark.asyncio
async def test_authz_clinical_abac_physician_mismatch_blocked() -> None:
    """Validate Tier 3 ABAC blocks physician who is not assigned to the encounter."""
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="77111222000198")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="11122233355")
        medico_responsavel = make_profissional(
            org.id,
            cpf="22233344488",
            email="dr.responsavel@hospital.com",
            papel=Role.MEDICO,
            crm="11223",
            crm_uf="SP",
        )
        medico_intruso = make_profissional(
            org.id,
            cpf="33344455577",
            email="dr.intruso@hospital.com",
            papel=Role.MEDICO,
            crm="44556",
            crm_uf="SP",
        )
        session.add_all([paciente, medico_responsavel, medico_intruso])
        await session.commit()
        await session.refresh(paciente)
        await session.refresh(medico_responsavel)
        await session.refresh(medico_intruso)

        atendimento = make_atendimento(
            organizacao_id=org.id,
            paciente_id=paciente.id,
            medico_id=medico_responsavel.id,
            status="EM_ATENDIMENTO",
            tcle_hash="d" * 64,
        )
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

    # Médico intruso tenta acessar prontuário do paciente do colega
    token_intruso = _create_token(medico_intruso.id, org.id, Role.MEDICO)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Tenant-ID": str(org.id)},
    ) as client:
        resp = await client.get(
            f"/consultations/{atendimento.id}/prontuario",
            headers={"Authorization": f"Bearer {token_intruso}"},
        )
        assert resp.status_code == 403
        err = cast("dict[str, object]", resp.json())
        assert err["title"] == "Forbidden"
        assert "não é o profissional assistente" in str(err["detail"])


@pytest.mark.asyncio
async def test_authz_clinical_abac_inactive_encounter_blocked() -> None:
    """Validate Tier 3 Clinical ABAC blocks access if encounter is already CONCLUIDO."""
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="77111222000197")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="11122233366")
        medico = make_profissional(
            org.id,
            cpf="22233344477",
            email="dr.concluido@hospital.com",
            papel=Role.MEDICO,
            crm="33445",
            crm_uf="SP",
        )
        session.add_all([paciente, medico])
        await session.commit()
        await session.refresh(paciente)
        await session.refresh(medico)

        atendimento = make_atendimento(
            organizacao_id=org.id,
            paciente_id=paciente.id,
            medico_id=medico.id,
            status="CONCLUIDO",  # Inactive
            tcle_hash="e" * 64,
        )
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

    token_medico = _create_token(medico.id, org.id, Role.MEDICO)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Tenant-ID": str(org.id)},
    ) as client:
        resp = await client.get(
            f"/consultations/{atendimento.id}/prontuario",
            headers={"Authorization": f"Bearer {token_medico}"},
        )
        assert resp.status_code == 403
        err = cast("dict[str, object]", resp.json())
        assert err["title"] == "Forbidden"
        assert "atendimento ativo" in str(err["detail"])


@pytest.mark.asyncio
async def test_authz_full_flow_access_granted() -> None:
    """Validate access when Macro RBAC, Tenant RLS, and Clinical ABAC are satisfied."""
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="77111222000196")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="11122233377")
        medico = make_profissional(
            org.id,
            cpf="22233344466",
            email="dr.sucesso@hospital.com",
            papel=Role.MEDICO,
            crm="55667",
            crm_uf="SP",
        )
        session.add_all([paciente, medico])
        await session.commit()
        await session.refresh(paciente)
        await session.refresh(medico)

        atendimento = make_atendimento(
            organizacao_id=org.id,
            paciente_id=paciente.id,
            medico_id=medico.id,
            status="EM_ATENDIMENTO",
            tcle_hash="f" * 64,
        )
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

    token_medico = _create_token(medico.id, org.id, Role.MEDICO)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Tenant-ID": str(org.id)},
    ) as client:
        # Test both /consultations/{id}/prontuario and /atendimentos/{id}/prontuario
        for endpoint in [
            f"/consultations/{atendimento.id}/prontuario",
            f"/atendimentos/{atendimento.id}/prontuario",
        ]:
            resp = await client.get(
                endpoint,
                headers={"Authorization": f"Bearer {token_medico}"},
            )
            assert resp.status_code == 200
            data = cast("dict[str, object]", resp.json())
            assert data["atendimento_id"] == str(atendimento.id)
            assert data["is_finalizado"] is False
            assert "evolucao" in data
            assert "documentos" in data
