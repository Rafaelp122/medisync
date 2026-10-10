"""Integration tests for S3 storage adapter and public document validation portal."""

from typing import cast
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.authz.roles import Role
from src.modules.consultation.domain.models import DocumentoClinico

from tests.factories.scenarios import seed_clinical_scenario
from tests.helpers import auth_headers

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.mark.asyncio
async def test_storage_presigned_url_and_validation_portal_full_flow(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate full flow: issue, sign, store in S3, validate via portal, download."""
    cenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="99888777000199",
        org_razao_social="Clinica Medisync Ltda",
        org_nome_fantasia="MediSync Telemedicina",
        paciente_nome="Maria Joana dos Santos",
        paciente_cpf="12345678900",
        medico_nome="Dr. Roberto Carlos de Souza",
        medico_cpf="98765432100",
        medico_email="dr.roberto@telemed.com.br",
        medico_crm="12345",
        medico_crm_uf="SP",
    )
    async_client.headers["X-Tenant-ID"] = str(cenario.organizacao.id)
    async_client.headers.update(
        auth_headers(Role.MEDICO, cenario.organizacao.id, cenario.medico.id)
    )
    client = async_client

    # 1. Emitir receita médica
    emit_resp = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/documents",
        json={
            "tipo_documento": "RECEITA_SIMPLES",
            "itens": [
                {
                    "medicamento": "Paracetamol 750mg",
                    "dosagem": "750mg comprimido",
                    "posologia": "Tomar 1 comprimido a cada 6 horas se febre.",
                    "duracao": "3 dias",
                }
            ],
        },
    )
    assert emit_resp.status_code == 201
    doc_data = cast("dict[str, object]", emit_resp.json())
    doc_id = cast("str", doc_data["id"])

    # 2. Assinar documento digitalmente com PAdES ICP-Brasil
    sign_resp = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/documents/{doc_id}/sign",
        json={
            "token": "valid-psc-oauth2-bearer-token",
            "provider": "fake",
            "certificate_alias": "dr-roberto-cert",
        },
    )
    assert sign_resp.status_code == 200

    # 3. Verificar persistência do documento no banco e chave S3
    doc_db = await db_session.get(DocumentoClinico, UUID(doc_id))
    assert doc_db is not None
    expected_key = (
        f"orgs/{cenario.organizacao.id}/consultations/"
        f"{cenario.atendimento.id}/documents/{doc_id}.pdf"
    )
    assert doc_db.chave_s3 == expected_key

    # 4. Validar documento publicamente via Portal de Validação (LGPD compliant)
    val_resp = await client.get(f"/api/v1/documents/validate/{doc_id}")
    assert val_resp.status_code == 200
    val_data = cast("dict[str, object]", val_resp.json())

    assert val_data["documento_id"] == doc_id
    assert val_data["tipo_documento"] == "RECEITA_SIMPLES"
    assert val_data["status_documento"] == "ASSINADO"
    assert val_data["assinatura_digital_valida"] is True
    assert val_data["conformidade_icp_brasil"] is True
    assert val_data["emissor_medico_nome"] == "Dr. Roberto Carlos de Souza"
    assert val_data["emissor_medico_crm"] == "12345"
    assert val_data["emissor_medico_uf"] == "SP"
    assert val_data["organizacao_nome"] == "MediSync Telemedicina"
    # LGPD masking verification
    assert val_data["paciente_nome_mascarado"] == "M**** J**** dos S*****"
    assert val_data["paciente_cpf_mascarado"] == "123.***.***-00"

    itens = cast("list[dict[str, object]]", val_data["itens"])
    assert len(itens) == 1
    assert itens[0]["medicamento"] == "Paracetamol 750mg"

    # 5. Obter URL pré-assinada sem redirecionamento (redirect=false)
    url_resp = await client.get(f"/api/v1/documents/download/{doc_id}?redirect=false")
    assert url_resp.status_code == 200
    url_data = cast("dict[str, object]", url_resp.json())
    assert url_data["documento_id"] == doc_id
    assert url_data["expires_in_seconds"] == 300
    assert "http" in cast("str", url_data["download_url"])
    assert url_data["chave_s3"] == expected_key

    # 6. Requisitar download com redirecionamento temporário 307
    redirect_resp = await client.get(
        f"/api/v1/documents/download/{doc_id}",
        follow_redirects=False,
    )
    assert redirect_resp.status_code == 307
    assert "location" in redirect_resp.headers
    location = redirect_resp.headers["location"]
    assert doc_id in location
    assert "expires_in=300" in location


@pytest.mark.asyncio
async def test_validation_portal_documento_nao_assinado(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate that un-signed document shows status EMITIDO and false validity."""
    cenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="99888777000198",
        paciente_cpf="33344455566",
        medico_cpf="22233344455",
        medico_email="dr.pedro@telemed.com.br",
        medico_crm="67890",
        medico_crm_uf="MG",
    )
    async_client.headers["X-Tenant-ID"] = str(cenario.organizacao.id)
    async_client.headers.update(
        auth_headers(Role.MEDICO, cenario.organizacao.id, cenario.medico.id)
    )
    client = async_client

    # Emitir atestado médico
    emit_resp = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/documents",
        json={
            "tipo_documento": "ATESTADO_MEDICO",
            "itens": [
                {
                    "medicamento": "Repouso Médico",
                    "dosagem": "2 dias",
                    "posologia": "Repouso domiciliar por incapacidade temporária.",
                    "duracao": "2 dias",
                }
            ],
        },
    )
    assert emit_resp.status_code == 201
    doc_id = cast("str", emit_resp.json()["id"])

    # Consultar no portal antes de assinar
    val_resp = await client.get(f"/api/v1/documents/validate/{doc_id}")
    assert val_resp.status_code == 200
    val_data = cast("dict[str, object]", val_resp.json())
    assert val_data["status_documento"] == "EMITIDO"
    assert val_data["assinado_em"] is None
    assert val_data["assinatura_digital_valida"] is False
    assert val_data["conformidade_icp_brasil"] is False


@pytest.mark.asyncio
async def test_validation_and_download_not_found(
    async_client: AsyncClient,
) -> None:
    """Validate 404 responses for non-existent documents or malformed UUIDs."""
    client = async_client
    random_id = str(uuid4())

    # Validate non-existent
    resp1 = await client.get(f"/api/v1/documents/validate/{random_id}")
    assert resp1.status_code == 404

    # Validate invalid token format
    resp2 = await client.get("/api/v1/documents/validate/not-a-uuid")
    assert resp2.status_code == 404

    # Download non-existent
    resp3 = await client.get(f"/api/v1/documents/download/{random_id}")
    assert resp3.status_code == 404

    # Download invalid token format
    resp4 = await client.get("/api/v1/documents/download/invalid-token-123")
    assert resp4.status_code == 404
