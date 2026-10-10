"""Integration tests for OWASP multi-tier authorization framework.

Enforces Tier 1 RBAC and Tier 3 Clinical ABAC/ReBAC context.
"""

from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.authz.roles import Role

from tests.factories.identity import make_profissional
from tests.factories.scenarios import seed_clinical_scenario
from tests.helpers import auth_headers

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.mark.asyncio
async def test_authz_unauthenticated_request_blocked(
    async_client: AsyncClient,
) -> None:
    """Validate requests without Authorization header are rejected with 401."""
    resp = await async_client.get(f"/api/v1/consultations/{uuid4()}/prontuario")
    assert resp.status_code == 401
    err = cast("dict[str, object]", resp.json())
    assert err["title"] == "Unauthorized"
    assert "não fornecida" in str(err["detail"])


@pytest.mark.asyncio
async def test_authz_macro_rbac_unauthorized_role_blocked(
    async_client: AsyncClient,
) -> None:
    """Validate Tier 1 Macro RBAC blocks non-medico roles with 403 Problem Details."""
    org_id = 77
    atend_id = uuid4()
    headers_base = {"X-Tenant-ID": str(org_id)}

    # 1. GESTOR_UNIDADE blocked
    resp_g = await async_client.get(
        f"/api/v1/consultations/{atend_id}/prontuario",
        headers={**headers_base, **auth_headers(Role.GESTOR_UNIDADE, org_id, uuid4())},
    )
    assert resp_g.status_code == 403
    err_g = cast("dict[str, object]", resp_g.json())
    assert err_g["title"] == "Forbidden"
    assert "GESTOR_UNIDADE" in str(err_g["detail"])

    # 2. FATURAMENTO blocked
    resp_f = await async_client.get(
        f"/api/v1/consultations/{atend_id}/prontuario",
        headers={**headers_base, **auth_headers(Role.FATURAMENTO, org_id, uuid4())},
    )
    assert resp_f.status_code == 403
    assert "FATURAMENTO" in str(cast("dict[str, object]", resp_f.json())["detail"])

    # 3. PACIENTE blocked
    resp_p = await async_client.get(
        f"/api/v1/consultations/{atend_id}/prontuario",
        headers={**headers_base, **auth_headers(Role.PACIENTE, org_id, uuid4())},
    )
    assert resp_p.status_code == 403
    assert "PACIENTE" in str(cast("dict[str, object]", resp_p.json())["detail"])


@pytest.mark.asyncio
async def test_authz_tenant_mismatch_blocked(
    async_client: AsyncClient,
) -> None:
    """Validate cross-tenant token usage is blocked with 403 Problem Details."""
    org_a_id = 81
    org_b_id = 82

    resp = await async_client.get(
        f"/api/v1/consultations/{uuid4()}/prontuario",
        headers={
            "X-Tenant-ID": str(org_b_id),  # Requesting Org B with Org A token
            **auth_headers(Role.MEDICO, org_a_id, uuid4()),
        },
    )
    assert resp.status_code == 403
    err = cast("dict[str, object]", resp.json())
    assert err["title"] == "Forbidden"
    assert "organização 81" in str(err["detail"])


@pytest.mark.asyncio
async def test_authz_clinical_abac_missing_tcle_blocked(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate Tier 3 ABAC blocks access if TCLE is not signed (CFM 2.314/2022)."""
    scenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="77111222000199",
        paciente_cpf="11122233344",
        medico_cpf="22233344499",
        medico_email="dr.fernando@hospital.com",
        medico_crm="98765",
        medico_crm_uf="SP",
        status_atendimento="EM_ATENDIMENTO",
        tcle_hash=None,
    )

    resp = await async_client.get(
        f"/api/v1/consultations/{scenario.atendimento.id}/prontuario",
        headers={
            "X-Tenant-ID": str(scenario.organizacao.id),
            **auth_headers(Role.MEDICO, scenario.organizacao.id, scenario.medico.id),
        },
    )
    assert resp.status_code == 403
    err = cast("dict[str, object]", resp.json())
    assert err["title"] == "Forbidden"
    assert "TCLE" in str(err["detail"])


@pytest.mark.asyncio
async def test_authz_clinical_abac_physician_mismatch_blocked(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate Tier 3 ABAC blocks physician who is not assigned to the encounter."""
    scenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="77111222000198",
        paciente_cpf="11122233355",
        medico_cpf="22233344488",
        medico_email="dr.responsavel@hospital.com",
        medico_crm="11223",
        medico_crm_uf="SP",
        status_atendimento="EM_ATENDIMENTO",
        tcle_hash="d" * 64,
    )

    medico_intruso = make_profissional(
        scenario.organizacao.id,
        cpf="33344455577",
        email="dr.intruso@hospital.com",
        papel=Role.MEDICO,
        crm="44556",
        crm_uf="SP",
    )
    db_session.add(medico_intruso)
    await db_session.commit()
    await db_session.refresh(medico_intruso)

    resp = await async_client.get(
        f"/api/v1/consultations/{scenario.atendimento.id}/prontuario",
        headers={
            "X-Tenant-ID": str(scenario.organizacao.id),
            **auth_headers(Role.MEDICO, scenario.organizacao.id, medico_intruso.id),
        },
    )
    assert resp.status_code == 403
    err = cast("dict[str, object]", resp.json())
    assert err["title"] == "Forbidden"
    assert "não é o profissional assistente" in str(err["detail"])


@pytest.mark.asyncio
async def test_authz_clinical_abac_concluded_encounter_read_granted(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate Tier 3 Clinical ABAC allows reading record if encounter is CONCLUIDO."""
    scenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="77111222000197",
        paciente_cpf="11122233366",
        medico_cpf="22233344477",
        medico_email="dr.concluido@hospital.com",
        medico_crm="33445",
        medico_crm_uf="SP",
        status_atendimento="CONCLUIDO",
        tcle_hash="e" * 64,
    )

    # 1. Read is granted for attending physician (CFM 1.821/2007)
    resp = await async_client.get(
        f"/api/v1/consultations/{scenario.atendimento.id}/prontuario",
        headers={
            "X-Tenant-ID": str(scenario.organizacao.id),
            **auth_headers(Role.MEDICO, scenario.organizacao.id, scenario.medico.id),
        },
    )
    assert resp.status_code == 200
    data = cast("dict[str, object]", resp.json())
    assert data["atendimento_id"] == str(scenario.atendimento.id)
    assert data["is_finalizado"] is True

    # 2. Mutation on CONCLUIDO is blocked with 403 Forbidden
    resp_mut = await async_client.post(
        f"/api/v1/consultations/{scenario.atendimento.id}/soap",
        json={"anamnese": "tentativa", "conduta": "tentativa"},
        headers={
            "X-Tenant-ID": str(scenario.organizacao.id),
            **auth_headers(Role.MEDICO, scenario.organizacao.id, scenario.medico.id),
        },
    )
    assert resp_mut.status_code == 403
    err = cast("dict[str, object]", resp_mut.json())
    assert err["title"] == "Forbidden"
    assert "atendimento já concluído" in str(err["detail"])


@pytest.mark.asyncio
async def test_authz_clinical_abac_cancelled_encounter_read_blocked(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate Tier 3 Clinical ABAC blocks reading cancelled encounters with 403."""
    scenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="77111222000195",
        paciente_cpf="11122233388",
        medico_cpf="22233344489",
        medico_email="dr.cancelado@hospital.com",
        medico_crm="33446",
        medico_crm_uf="SP",
        status_atendimento="CANCELADO_PACIENTE",
        tcle_hash="c" * 64,
    )

    resp = await async_client.get(
        f"/api/v1/consultations/{scenario.atendimento.id}/prontuario",
        headers={
            "X-Tenant-ID": str(scenario.organizacao.id),
            **auth_headers(Role.MEDICO, scenario.organizacao.id, scenario.medico.id),
        },
    )
    assert resp.status_code == 403
    err = cast("dict[str, object]", resp.json())
    assert err["title"] == "Forbidden"
    assert "atendimento ativo" in str(err["detail"])


@pytest.mark.asyncio
async def test_authz_full_flow_access_granted(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate access when Macro RBAC, Tenant RLS, and Clinical ABAC are satisfied."""
    scenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="77111222000196",
        paciente_cpf="11122233377",
        medico_cpf="22233344466",
        medico_email="dr.sucesso@hospital.com",
        medico_crm="55667",
        medico_crm_uf="SP",
        status_atendimento="EM_ATENDIMENTO",
        tcle_hash="f" * 64,
    )

    resp = await async_client.get(
        f"/api/v1/consultations/{scenario.atendimento.id}/prontuario",
        headers={
            "X-Tenant-ID": str(scenario.organizacao.id),
            **auth_headers(Role.MEDICO, scenario.organizacao.id, scenario.medico.id),
        },
    )
    assert resp.status_code == 200
    data = cast("dict[str, object]", resp.json())
    assert data["atendimento_id"] == str(scenario.atendimento.id)
    assert data["is_finalizado"] is False
    assert "evolucao" in data
    assert "documentos" in data
