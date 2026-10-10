"""Integration tests for PEP transaction ownership (service commits once)."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import async_session_factory
from src.core.errors import NotFoundError
from src.modules.consultation.application.dtos import (
    CriarItemPrescricaoDTO,
    EmitirDocumentoClinicoCommand,
    FinalizarConsultaCommand,
    RegistrarEvolucaoSOAPCommand,
)
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
)
from src.modules.consultation.domain.models import DocumentoClinico, EvolucaoClinica

from tests.factories.queue import make_atendimento
from tests.factories.scenarios import seed_clinical_scenario
from tests.helpers import make_pep_service

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.mark.asyncio
async def test_salvar_evolucao_soap_service_commit_visivel_outra_sessao(
    db_session: AsyncSession,
) -> None:
    """Service commit persists SOAP without router commit (separate session)."""
    cenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="11111111000111",
        paciente_cpf="11111111111",
        medico_cpf="22222222211",
        medico_email="tx-soap@medisync.local",
    )
    atend_id = cenario.atendimento.id
    org_id = cenario.organizacao.id
    medico_id = cenario.medico.id

    async with async_session_factory() as s1:
        svc = make_pep_service(s1)
        cmd = RegistrarEvolucaoSOAPCommand(
            atendimento_id=atend_id,
            organizacao_id=org_id,
            medico_id=medico_id,
            anamnese="Queixa de tosse há 2 dias.",
            conduta="Hidratação e sintomáticos.",
            exame_fisico_virtual="Bom estado geral.",
            cid10_principal="J00",
        )
        await svc.salvar_evolucao_soap(cmd)
        # Sem commit no router: service deve ter commitado.

    async with async_session_factory() as s2:
        res = await s2.execute(
            select(EvolucaoClinica).where(EvolucaoClinica.atendimento_id == atend_id)
        )
        evolucao = res.scalar_one_or_none()
        assert evolucao is not None
        assert evolucao.anamnese == "Queixa de tosse há 2 dias."
        assert evolucao.cid10_principal == "J00"


@pytest.mark.asyncio
async def test_emitir_documento_service_commit_visivel_outra_sessao(
    db_session: AsyncSession,
) -> None:
    """Service commit persists document+items without router commit."""
    cenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="22222222000111",
        paciente_cpf="33333333311",
        medico_cpf="44444444411",
        medico_email="tx-doc@medisync.local",
    )
    atend_id = cenario.atendimento.id
    org_id = cenario.organizacao.id
    medico_id = cenario.medico.id

    async with async_session_factory() as s1:
        svc = make_pep_service(s1)
        cmd = EmitirDocumentoClinicoCommand(
            atendimento_id=atend_id,
            organizacao_id=org_id,
            medico_id=medico_id,
            tipo_documento="RECEITA_SIMPLES",
            itens=[
                CriarItemPrescricaoDTO(
                    medicamento="Dipirona 500mg",
                    dosagem="1 cp",
                    posologia="1 cp se dor",
                    duracao="3 dias",
                )
            ],
        )
        doc = await svc.emitir_documento(cmd)
        doc_id = doc.id

    async with async_session_factory() as s2:
        res = await s2.execute(
            select(DocumentoClinico).where(DocumentoClinico.id == doc_id)
        )
        persisted = res.scalar_one_or_none()
        assert persisted is not None
        assert persisted.tipo_documento == "RECEITA_SIMPLES"
        assert len(persisted.itens) == 1
        assert persisted.itens[0].medicamento == "Dipirona 500mg"


@pytest.mark.asyncio
async def test_finalizar_consulta_service_commit_visivel_outra_sessao(
    db_session: AsyncSession,
) -> None:
    """Service commit persists finalization (atendimento CONCLUIDO)."""
    cenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="33333333000111",
        paciente_cpf="55555555511",
        medico_cpf="66666666611",
        medico_email="tx-fin@medisync.local",
    )
    atend_id = cenario.atendimento.id
    org_id = cenario.organizacao.id
    medico_id = cenario.medico.id

    async with async_session_factory() as s1:
        svc = make_pep_service(s1)
        await svc.salvar_evolucao_soap(
            RegistrarEvolucaoSOAPCommand(
                atendimento_id=atend_id,
                organizacao_id=org_id,
                medico_id=medico_id,
                anamnese="Cefaleia leve.",
                conduta="Sintomático e repouso.",
            )
        )

    async with async_session_factory() as s1b:
        svc = make_pep_service(s1b)
        await svc.finalizar_consulta(
            FinalizarConsultaCommand(
                atendimento_id=atend_id,
                organizacao_id=org_id,
                medico_id=medico_id,
            )
        )

    async with async_session_factory() as s2:
        res = await s2.execute(
            text("SELECT status FROM atendimentos WHERE id = :id"),
            {"id": atend_id},
        )
        status_val = res.scalar_one_or_none()
        assert status_val is not None
        assert str(status_val).strip().upper() == "CONCLUIDO"


@pytest.mark.asyncio
async def test_assinar_documento_service_commit_visivel_outra_sessao(
    db_session: AsyncSession,
) -> None:
    """Service commit persists signature without router commit."""
    cenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="44444444000111",
        paciente_cpf="77777777711",
        medico_cpf="88888888811",
        medico_email="tx-sign@medisync.local",
    )
    atend_id = cenario.atendimento.id
    org_id = cenario.organizacao.id
    medico_id = cenario.medico.id

    signer = AsyncMock()
    signer.assinar_pdf.return_value = b"%PDF-signed-bytes%"
    storage = AsyncMock()
    storage.obter_documento.return_value = b"%PDF-fake%"
    storage.salvar_documento.return_value = None

    async with async_session_factory() as s1:
        svc = make_pep_service(s1, signer=signer, storage=storage)
        doc = await svc.emitir_documento(
            EmitirDocumentoClinicoCommand(
                atendimento_id=atend_id,
                organizacao_id=org_id,
                medico_id=medico_id,
                tipo_documento="RECEITA_SIMPLES",
                itens=[
                    CriarItemPrescricaoDTO(
                        medicamento="Dipirona 500mg",
                        dosagem="1 cp",
                        posologia="1 cp se dor",
                    )
                ],
            )
        )
        doc_id = doc.id

    async with async_session_factory() as s1b:
        svc = make_pep_service(s1b, signer=signer, storage=storage)
        creds = DoctorCertificateCredentials(
            token="valid-token", provider="fake", certificate_alias="cert-tx"
        )
        doc_signed, signed_bytes = await svc.documento_service.assinar(
            doc_id, atend_id, creds
        )
        assert signed_bytes == b"%PDF-signed-bytes%"
        assert doc_signed.sha256_hash is not None

    async with async_session_factory() as s2:
        res = await s2.execute(
            select(DocumentoClinico).where(DocumentoClinico.id == doc_id)
        )
        persisted = res.scalar_one_or_none()
        assert persisted is not None
        assert persisted.chave_s3.startswith(f"orgs/{org_id}/consultations/")
        assert persisted.assinado_em is not None
        assert len(persisted.sha256_hash) == 64


@pytest.mark.asyncio
async def test_assinar_documento_outro_atendimento_404_signer_nao_chamado(
    db_session: AsyncSession,
) -> None:
    """Ownership before PSC: wrong atendimento -> 404 and signer spy not called."""
    cenario = await seed_clinical_scenario(
        db_session,
        org_cnpj="55555555000111",
        paciente_cpf="99999999911",
        medico_cpf="00011122211",
        medico_email="tx-own@medisync.local",
    )
    atend_a = cenario.atendimento.id
    org_id = cenario.organizacao.id
    medico_id = cenario.medico.id

    atendimento_b = make_atendimento(
        organizacao_id=org_id,
        paciente_id=cenario.paciente.id,
        status="EM_ATENDIMENTO",
    )
    db_session.add(atendimento_b)
    await db_session.commit()
    await db_session.refresh(atendimento_b)
    atend_b = atendimento_b.id

    signer_spy = AsyncMock()
    signer_spy.assinar_pdf.return_value = b"%PDF-should-not-happen%"
    storage = AsyncMock()
    storage.obter_documento.return_value = b"%PDF-fake%"
    storage.salvar_documento.return_value = None

    async with async_session_factory() as s1:
        svc = make_pep_service(s1, signer=signer_spy, storage=storage)
        doc = await svc.emitir_documento(
            EmitirDocumentoClinicoCommand(
                atendimento_id=atend_a,
                organizacao_id=org_id,
                medico_id=medico_id,
                tipo_documento="RECEITA_SIMPLES",
                itens=[
                    CriarItemPrescricaoDTO(
                        medicamento="Paracetamol 500mg",
                        dosagem="1 cp",
                        posologia="1 cp se dor",
                    )
                ],
            )
        )
        doc_id = doc.id
        original_hash = doc.sha256_hash

    async with async_session_factory() as s2:
        svc2 = make_pep_service(s2, signer=signer_spy, storage=storage)
        creds = DoctorCertificateCredentials(token="tok", provider="fake")
        with pytest.raises(NotFoundError):
            await svc2.documento_service.assinar(doc_id, atend_b, creds)

    signer_spy.assinar_pdf.assert_not_called()
    storage.salvar_documento.assert_not_called()

    async with async_session_factory() as s3:
        res = await s3.execute(
            select(DocumentoClinico).where(DocumentoClinico.id == doc_id)
        )
        persisted = res.scalar_one_or_none()
        assert persisted is not None
        assert persisted.sha256_hash == original_hash
