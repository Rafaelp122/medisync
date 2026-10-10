"""Integration: public validation without tenant bypasses RLS via superuser."""

from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.context import tenant_context
from src.modules.consultation.domain.models import (
    DocumentoClinico,
    TipoDocumentoClinico,
)

from tests.factories.scenarios import seed_clinical_scenario

pytestmark = pytest.mark.usefixtures("clean_db")

_SAMPLE_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@pytest.mark.asyncio
async def test_public_validation_without_tenant_bypasses_rls(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate public validation and download succeed without tenant header."""
    scenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="77788899000111",
        org_razao_social="Clinica Publica LTDA",
        org_nome_fantasia="Clinica Publica",
        paciente_nome="Maria Joana dos Santos",
        paciente_cpf="12345678900",
        medico_nome="Dr. Roberto Carlos de Souza",
        medico_cpf="98765432100",
        medico_email="pub@med.local",
        medico_crm="12345",
        medico_crm_uf="SP",
        status_atendimento="EM_ATENDIMENTO",
    )

    with tenant_context(scenario.organizacao.id):
        doc = DocumentoClinico(
            organizacao_id=scenario.organizacao.id,
            atendimento_id=scenario.atendimento.id,
            medico_id=scenario.medico.id,
            tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
            chave_s3="placeholder.pdf",
            sha256_hash=_SAMPLE_HASH,
        )
        db_session.add(doc)
        await db_session.flush()
        doc.chave_s3 = (
            f"orgs/{scenario.organizacao.id}/consultations/"
            f"{scenario.atendimento.id}/documents/{doc.id}.pdf"
        )
        await db_session.commit()
        doc_id = str(doc.id)

    # Public calls WITHOUT X-Tenant-ID must still see the document (superuser bypass)
    val = await async_client.get(f"/api/v1/documents/validate/{doc_id}")
    assert val.status_code == 200, val.text
    data = cast("dict[str, object]", val.json())
    assert data["documento_id"] == doc_id
    assert data["status_documento"] == "EMITIDO"
    assert data["paciente_cpf_mascarado"] == "123.***.***-00"
    assert data["paciente_nome_mascarado"] == "M**** J**** dos S*****"

    dl = await async_client.get(f"/api/v1/documents/download/{doc_id}?redirect=false")
    assert dl.status_code == 200, dl.text
    dl_data = cast("dict[str, object]", dl.json())
    assert dl_data["documento_id"] == doc_id
    assert "http" in cast("str", dl_data["download_url"])

    notfound = await async_client.get(f"/api/v1/documents/validate/{uuid4()}")
    assert notfound.status_code == 404
