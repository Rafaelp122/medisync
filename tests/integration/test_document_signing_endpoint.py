"""Integration tests for ICP-Brasil PAdES document signing endpoint."""

import io
from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import async_validate_pdf_signature
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.authz.roles import Role

from tests.factories.scenarios import seed_clinical_scenario
from tests.helpers import auth_headers

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.mark.asyncio
async def test_assinar_documento_clinico_pades_flow(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate full flow: issue document, sign with PAdES, download signed PDF."""
    cenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="55555555000103",
        paciente_cpf="77777777701",
        medico_cpf="88888888801",
    )
    async_client.headers["X-Tenant-ID"] = str(cenario.organizacao.id)
    async_client.headers.update(
        auth_headers(Role.MEDICO, cenario.organizacao.id, cenario.medico.id)
    )
    client = async_client

    # 1. Emitir receita simples
    emit_resp = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/documents",
        json={
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
        f"/api/v1/consultations/{cenario.atendimento.id}/documents/{doc_id}/sign",
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
        f"/api/v1/consultations/{cenario.atendimento.id}/documents/{doc_id}/pdf"
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
async def test_assinar_documento_consultation_finalizada_bloqueado(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate signing is rejected with 403 Forbidden if consultation finalized."""
    cenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="55555555000104",
        paciente_cpf="77777777702",
        medico_cpf="88888888802",
    )
    async_client.headers["X-Tenant-ID"] = str(cenario.organizacao.id)
    async_client.headers.update(
        auth_headers(Role.MEDICO, cenario.organizacao.id, cenario.medico.id)
    )
    client = async_client

    # Emitir documento
    emit_resp = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/documents",
        json={
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
        f"/api/v1/consultations/{cenario.atendimento.id}/soap",
        json={
            "anamnese": "Paciente refere cefaleia de leve intensidade.",
            "conduta": "Prescrito sintomático e repouso.",
        },
    )
    assert soap_resp.status_code == 200

    # Finalizar consulta
    fin_resp = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/finalize",
        json={},
    )
    assert fin_resp.status_code == 200

    # Tentar assinar documento após finalização -> 403 Forbidden
    sign_resp = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/documents/{doc_id}/sign",
        json={
            "token": "valid-token",
            "provider": "fake",
        },
    )
    assert sign_resp.status_code == 403
    err_body = sign_resp.json()
    assert "atendimento já concluído" in err_body["detail"]


@pytest.mark.asyncio
async def test_assinar_documento_erros_validacao_e_nao_encontrado(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate 404 for non-existent documents and 422 for invalid parameters."""
    cenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="55555555000105",
        paciente_cpf="77777777703",
        medico_cpf="88888888803",
    )
    async_client.headers["X-Tenant-ID"] = str(cenario.organizacao.id)
    async_client.headers.update(
        auth_headers(Role.MEDICO, cenario.organizacao.id, cenario.medico.id)
    )
    client = async_client

    # 1. Documento não encontrado -> 404
    non_existent_doc = uuid4()
    resp_404 = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/documents/{non_existent_doc}/sign",
        json={"token": "some-token", "provider": "fake"},
    )
    assert resp_404.status_code == 404

    # 2. Token vazio -> 422
    emit_resp = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/documents",
        json={
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
        f"/api/v1/consultations/{cenario.atendimento.id}/documents/{doc_id}/sign",
        json={"token": "   ", "provider": "fake"},
    )
    assert resp_422.status_code == 422
