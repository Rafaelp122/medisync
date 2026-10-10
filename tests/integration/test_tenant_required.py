"""Integration tests for mandatory TenantDep without silent fallback."""

from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories.scenarios import seed_multi_tenant_orgs

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.mark.asyncio
async def test_soap_sem_tenant_retorna_400(
    async_client: AsyncClient,
) -> None:
    """POST soap sem X-Tenant-ID -> 400 TENANT_INVALIDO (sem fallback para 1)."""
    resp = await async_client.post(
        f"/api/v1/consultations/{uuid4()}/soap",
        json={
            "medico_id": str(uuid4()),
            "anamnese": "Queixa teste",
            "conduta": "Conduta teste",
        },
    )
    assert resp.status_code == 400
    body = cast("dict[str, object]", resp.json())
    assert body["code"] == "TENANT_INVALIDO"
    assert body["status"] == 400


@pytest.mark.asyncio
async def test_soap_body_organizacao_divergente_retorna_403(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Body organizacao_id divergente do header -> 403 Forbidden."""
    org_a, org_b = await seed_multi_tenant_orgs(db_session)

    resp = await async_client.post(
        f"/api/v1/consultations/{uuid4()}/soap",
        json={
            "medico_id": str(uuid4()),
            "anamnese": "Queixa teste",
            "conduta": "Conduta teste",
            "organizacao_id": org_b.id,
        },
        headers={"X-Tenant-ID": str(org_a.id)},
    )
    assert resp.status_code == 403
    body = cast("dict[str, object]", resp.json())
    assert body["code"] == "FORBIDDEN"
    assert body["status"] == 403
