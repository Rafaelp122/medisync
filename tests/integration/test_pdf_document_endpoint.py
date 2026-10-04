"""Integration tests for clinical document PDF generation and download endpoint."""

from collections.abc import AsyncGenerator
from typing import cast
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from src.core.database import async_session_factory
from src.main import app

from tests.factories.identity import (
    make_organizacao,
    make_paciente,
    make_profissional,
)
from tests.factories.queue import make_atendimento
from tests.helpers import clean_database_tables


@pytest.fixture(autouse=True)
async def setup_consultation_pdf_db() -> AsyncGenerator[None, None]:
    """Ensure database schema is ready before running tests and clean up after."""
    await clean_database_tables()
    yield
    await clean_database_tables()


@pytest.mark.asyncio
async def test_obter_documento_pdf_endpoint() -> None:
    """Validate PDF generation and download endpoint returns compliant PDF/A."""
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="44444444000102")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="55555555501")
        medico = make_profissional(
            org.id,
            cpf="66666666601",
            email="dr.marcos@telemed.com.br",
            papel="MEDICO",
            crm="98765",
            crm_uf="SP",
        )
        session.add_all([paciente, medico])
        await session.commit()
        await session.refresh(paciente)
        await session.refresh(medico)

        atendimento = make_atendimento(
            organizacao_id=org.id,
            paciente_id=paciente.id,
            status="EM_ATENDIMENTO",
        )
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Tenant-ID": str(org.id)},
    ) as client:
        # 1. Emitir receita simples
        emit_resp = await client.post(
            f"/consultations/{atendimento.id}/documents",
            json={
                "medico_id": str(medico.id),
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
            f"/consultations/{atendimento.id}/documents/{doc_id}/pdf"
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
            f"/consultations/{atendimento.id}/documents/{non_existent_id}/pdf"
        )
        assert not_found_resp.status_code == 404
