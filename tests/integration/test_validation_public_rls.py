"""Integration: public validation without tenant bypasses RLS via superuser."""

from collections.abc import AsyncGenerator
from typing import cast
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from src.core.context import tenant_context
from src.core.database import async_session_factory
from src.main import app
from src.modules.consultation.domain.models import (
    DocumentoClinico,
    TipoDocumentoClinico,
)

from tests.factories.identity import (
    make_organizacao,
    make_paciente,
    make_profissional,
)
from tests.factories.queue import make_atendimento
from tests.helpers import clean_database_tables

_SAMPLE_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@pytest.fixture(autouse=True)
async def _clean() -> AsyncGenerator[None, None]:
    await clean_database_tables()
    yield
    await clean_database_tables()


@pytest.mark.asyncio
async def test_public_validation_without_tenant_bypasses_rls() -> None:
    async with async_session_factory() as session:
        org = make_organizacao(
            cnpj="77788899000111",
            razao_social="Clinica Publica LTDA",
            nome_fantasia="Clinica Publica",
        )
        session.add(org)
        await session.commit()
        await session.refresh(org)

    with tenant_context(org.id):
        async with async_session_factory() as session:
            pac = make_paciente(
                org.id, nome_completo="Maria Joana dos Santos", cpf="12345678900"
            )
            med = make_profissional(
                org.id,
                nome_completo="Dr. Roberto Carlos de Souza",
                cpf="98765432100",
                email="pub@med.local",
                papel="MEDICO",
                crm="12345",
                crm_uf="SP",
            )
            session.add_all([pac, med])
            await session.commit()
            await session.refresh(pac)
            await session.refresh(med)
            atend = make_atendimento(
                organizacao_id=org.id, paciente_id=pac.id, status="EM_ATENDIMENTO"
            )
            session.add(atend)
            await session.commit()
            await session.refresh(atend)
            doc = DocumentoClinico(
                organizacao_id=org.id,
                atendimento_id=atend.id,
                medico_id=med.id,
                tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
                chave_s3=f"orgs/{org.id}/consultations/{atend.id}/documents/placeholder.pdf",
                sha256_hash=_SAMPLE_HASH,
            )
            # fix chave after id generated
            session.add(doc)
            await session.flush()
            doc.chave_s3 = (
                f"orgs/{org.id}/consultations/{atend.id}/documents/{doc.id}.pdf"
            )
            await session.commit()
            doc_id = str(doc.id)

    # Public calls WITHOUT X-Tenant-ID must still see the document (superuser bypass)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        val = await client.get(f"/api/v1/documents/validate/{doc_id}")
        assert val.status_code == 200, val.text
        data = cast("dict[str, object]", val.json())
        assert data["documento_id"] == doc_id
        assert data["status_documento"] == "ASSINADO"
        assert data["paciente_cpf_mascarado"] == "123.***.***-00"
        assert data["paciente_nome_mascarado"] == "M**** J**** dos S*****"

        dl = await client.get(f"/api/v1/documents/download/{doc_id}?redirect=false")
        assert dl.status_code == 200, dl.text
        dl_data = cast("dict[str, object]", dl.json())
        assert dl_data["documento_id"] == doc_id
        assert "http" in cast("str", dl_data["download_url"])

        notfound = await client.get(f"/api/v1/documents/validate/{uuid4()}")
        assert notfound.status_code == 404
