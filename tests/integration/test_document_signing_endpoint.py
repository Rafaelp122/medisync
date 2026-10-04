"""Integration tests for ICP-Brasil PAdES document signing endpoint."""

import io
from collections.abc import AsyncGenerator
from typing import cast
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import async_validate_pdf_signature
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
async def setup_consultation_sign_db() -> AsyncGenerator[None, None]:
    """Ensure database schema is ready before running tests and clean up after."""
    await clean_database_tables()
    yield
    await clean_database_tables()


@pytest.mark.asyncio
async def test_assinar_documento_clinico_pades_flow() -> None:
    """Validate full flow: issue document, sign with PAdES, download signed PDF."""
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="55555555000103")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="77777777701")
        medico = make_profissional(
            org.id,
            cpf="88888888801",
            email="dr.antonio@telemed.com.br",
            papel="MEDICO",
            crm="54321",
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
                        "medicamento": "Amoxicilina 500mg",
                        "dosagem": "500mg cápsula",
                        "posologia": "Tomar 1 cápsula a cada 8h por 7 dias.",
                        "duracao": "7 dias",
                    }
                ],
            },
        )
        assert emit_resp.status_code == 201
        doc_data = cast("dict[str, object]", emit_resp.json())
        doc_id = cast("str", doc_data["id"])
        original_hash = cast("str", doc_data["sha256_hash"])

        # 2. Assinar documento com PAdES ICP-Brasil via PSC
        sign_resp = await client.post(
            f"/consultations/{atendimento.id}/documents/{doc_id}/sign",
            json={
                "token": "valid-psc-oauth2-bearer-token",
                "provider": "fake",
                "certificate_alias": "dr-antonio-cert",
            },
        )
        assert sign_resp.status_code == 200
        sign_data = cast("dict[str, object]", sign_resp.json())
        assert sign_data["documento_id"] == doc_id
        assert sign_data["tipo_documento"] == "RECEITA_SIMPLES"
        assert sign_data["assinado_em"] is not None
        assert sign_data["tamanho_bytes"] is not None
        assert cast("int", sign_data["tamanho_bytes"]) > 0

        signed_hash = cast("str", sign_data["sha256_hash"])
        assert len(signed_hash) == 64
        # Hash must be updated with the digital signature envelope
        assert signed_hash != original_hash

        # 3. Baixar PDF assinado e validar criptograficamente
        pdf_resp = await client.get(
            f"/consultations/{atendimento.id}/documents/{doc_id}/pdf"
        )
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers["content-type"] == "application/pdf"

        signed_bytes = pdf_resp.content
        reader = PdfFileReader(io.BytesIO(signed_bytes))
        assert len(reader.embedded_signatures) == 1
        sig = reader.embedded_signatures[0]
        assert sig.field_name.startswith("Assinatura_ICP_Brasil")

        status = await async_validate_pdf_signature(sig)
        assert status.intact is True
        assert status.valid is True


@pytest.mark.asyncio
async def test_assinar_documento_consultation_finalizada_bloqueado() -> None:
    """Validate signing is rejected with 409 Conflict if consultation finalized."""
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="55555555000104")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="77777777702")
        medico = make_profissional(
            org.id,
            cpf="88888888802",
            email="dr.carlos@telemed.com.br",
            papel="MEDICO",
            crm="54322",
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
        # Emitir documento
        emit_resp = await client.post(
            f"/consultations/{atendimento.id}/documents",
            json={
                "medico_id": str(medico.id),
                "tipo_documento": "RECEITA_SIMPLES",
                "itens": [
                    {
                        "medicamento": "Dipirona 500mg",
                        "dosagem": "500mg",
                        "posologia": "1 comprimido",
                        "duracao": "3 dias",
                    }
                ],
            },
        )
        assert emit_resp.status_code == 201
        doc_id = emit_resp.json()["id"]

        # Salvar evolução SOAP necessária antes de finalizar
        soap_resp = await client.post(
            f"/consultations/{atendimento.id}/soap",
            json={
                "medico_id": str(medico.id),
                "anamnese": "Paciente refere cefaleia de leve intensidade.",
                "conduta": "Prescrito sintomático e repouso.",
            },
        )
        assert soap_resp.status_code == 200

        # Finalizar consulta
        fin_resp = await client.post(
            f"/consultations/{atendimento.id}/finalize",
            json={"medico_id": str(medico.id)},
        )
        assert fin_resp.status_code == 200

        # Tentar assinar documento após finalização -> 409 Conflict
        sign_resp = await client.post(
            f"/consultations/{atendimento.id}/documents/{doc_id}/sign",
            json={
                "token": "valid-token",
                "provider": "fake",
            },
        )
        assert sign_resp.status_code == 409
        err_body = sign_resp.json()
        assert "já finalizada" in err_body["detail"]


@pytest.mark.asyncio
async def test_assinar_documento_erros_validacao_e_nao_encontrado() -> None:
    """Validate 404 for non-existent documents and 422 for invalid parameters."""
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="55555555000105")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="77777777703")
        medico = make_profissional(
            org.id,
            cpf="88888888803",
            email="dra.lucia@telemed.com.br",
            papel="MEDICO",
            crm="54323",
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
        # 1. Documento não encontrado -> 404
        non_existent_doc = uuid4()
        resp_404 = await client.post(
            f"/consultations/{atendimento.id}/documents/{non_existent_doc}/sign",
            json={"token": "some-token", "provider": "fake"},
        )
        assert resp_404.status_code == 404

        # 2. Token vazio -> 422
        emit_resp = await client.post(
            f"/consultations/{atendimento.id}/documents",
            json={
                "medico_id": str(medico.id),
                "tipo_documento": "RECEITA_SIMPLES",
                "itens": [
                    {
                        "medicamento": "Paracetamol 750mg",
                        "dosagem": "750mg",
                        "posologia": "1 cp se dor",
                    }
                ],
            },
        )
        assert emit_resp.status_code == 201
        doc_id = emit_resp.json()["id"]

        resp_422 = await client.post(
            f"/consultations/{atendimento.id}/documents/{doc_id}/sign",
            json={"token": "   ", "provider": "fake"},
        )
        assert resp_422.status_code == 422
