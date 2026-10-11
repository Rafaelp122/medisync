"""Integration tests for mandatory TenantDep without silent fallback."""

from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.authz.roles import Role

from tests.factories.identity import make_organizacao
from tests.factories.scenarios import (
    seed_clinical_scenario,
)
from tests.helpers import auth_headers

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.mark.asyncio
async def test_endpoint_sem_tenant_retorna_400(
    async_client: AsyncClient,
) -> None:
    """Endpoint com TenantDep sem X-Tenant-ID e sem Bearer token
    -> 400 TENANT_INVALIDO (sem fallback para 1).
    """
    async_client.headers.pop("X-Tenant-ID", None)

    sample_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    resp = await async_client.post(
        "/api/v1/onboarding/fase-1",
        json={
            "nome_completo": "Paciente Sem Tenant",
            "data_nascimento": "1990-01-01",
            "telefone": "11987654321",
            "queixa_principal": "Febre",
            "tcle_hash": sample_hash,
            "cpf": "11144477735",
        },
    )
    assert resp.status_code == 400
    body = cast("dict[str, object]", resp.json())
    assert body["code"] == "TENANT_INVALIDO"
    assert body["status"] == 400


@pytest.mark.asyncio
async def test_soap_sem_header_tenant_infere_do_bearer_token(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """POST soap sem X-Tenant-ID infere tenant do Bearer token (Issue #41)."""
    cenario = await seed_clinical_scenario(db_session)
    async_client.headers.pop("X-Tenant-ID", None)

    resp = await async_client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/soap",
        json={
            "anamnese": "Queixa teste",
            "conduta": "Conduta teste",
        },
        headers=auth_headers(Role.MEDICO, cenario.organizacao.id, cenario.medico.id),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_soap_body_organizacao_divergente_retorna_403(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Body organizacao_id divergente do header -> 403 Forbidden."""
    cenario = await seed_clinical_scenario(db_session)
    org_b = make_organizacao(
        id=cenario.organizacao.id + 1,
        cnpj="99988877000199",
        razao_social="Hospital Org B",
    )
    db_session.add(org_b)
    await db_session.commit()
    await db_session.refresh(org_b)

    resp = await async_client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/soap",
        json={
            "anamnese": "Queixa teste",
            "conduta": "Conduta teste",
            "organizacao_id": org_b.id,
        },
        headers={
            "X-Tenant-ID": str(cenario.organizacao.id),
            **auth_headers(Role.MEDICO, cenario.organizacao.id, cenario.medico.id),
        },
    )
    assert resp.status_code == 403
    body = cast("dict[str, object]", resp.json())
    assert body["code"] == "FORBIDDEN"
    assert body["status"] == 403
