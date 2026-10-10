"""Integration tests for clinical document PDF generation and download endpoint."""

from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories.scenarios import seed_clinical_scenario

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.mark.asyncio
async def test_obter_documento_pdf_endpoint(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate PDF generation and download endpoint returns compliant PDF/A."""
    cenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="44444444000102",
        paciente_cpf="55555555501",
        medico_cpf="66666666601",
    )
    async_client.headers["X-Tenant-ID"] = str(cenario.organizacao.id)
    client = async_client

    # 1. Emitir receita simples
    emit_resp = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/documents",
        json={
            "medico_id": str(cenario.medico.id),
            "tipo_documento": "RECEITA_SIMPLES",
            "itens": [
                {
                    "medicamento": "Dipirona Monoidratada",
                    "dosagem": "500mg/mL",
                    "posologia": "Tomar 30 gotas a cada 6h se dor.",
                    "duracao": "3 dias",
                }
            ],
        },
    )
    assert emit_resp.status_code == 201
    doc_data = cast("dict[str, object]", emit_resp.json())
    doc_id = cast("str", doc_data["id"])

    # 2. Requisitar PDF gerado
    pdf_resp = await client.get(
        f"/api/v1/consultations/{cenario.atendimento.id}/documents/{doc_id}/pdf"
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert f'filename="{doc_id}.pdf"' in pdf_resp.headers["content-disposition"]

    pdf_bytes = pdf_resp.content
    assert pdf_bytes.startswith(b"%PDF-")
    assert b"pdfaid:part>1" in pdf_bytes
    assert b"GTS_PDFA1" in pdf_bytes
    assert doc_id.encode() in pdf_bytes

    # 3. Requisitar PDF com ID inexistente -> 404
    non_existent_id = uuid4()
    not_found_resp = await client.get(
        f"/api/v1/consultations/{cenario.atendimento.id}/documents/{non_existent_id}/pdf"
    )
    assert not_found_resp.status_code == 404
