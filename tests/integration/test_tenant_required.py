"""Integration tests for mandatory TenantDep without silent fallback."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app


@pytest.mark.asyncio
async def test_soap_sem_tenant_retorna_400() -> None:
    """POST soap sem X-Tenant-ID -> 400 TENANT_INVALIDO (sem fallback para 1)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/consultations/{uuid4()}/soap",
            json={
                "medico_id": str(uuid4()),
                "anamnese": "Queixa teste",
                "conduta": "Conduta teste",
            },
        )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "TENANT_INVALIDO"
    assert body["status"] == 400


@pytest.mark.asyncio
async def test_soap_body_organizacao_divergente_retorna_403() -> None:
    """Body organizacao_id divergente do header -> 403 Forbidden."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Tenant-ID": "10"},
    ) as client:
        resp = await client.post(
            f"/api/v1/consultations/{uuid4()}/soap",
            json={
                "medico_id": str(uuid4()),
                "anamnese": "Queixa teste",
                "conduta": "Conduta teste",
                "organizacao_id": 999,
            },
        )
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "FORBIDDEN"
    assert body["status"] == 403
