"""Integration tests for PEP transaction ownership (service commits once)."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import select, text
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

from tests.factories.identity import (
    make_organizacao,
    make_paciente,
    make_profissional,
)
from tests.factories.queue import make_atendimento
from tests.helpers import clean_database_tables, make_pep_service


@pytest.fixture(autouse=True)
async def setup_pep_tx_db() -> AsyncGenerator[None, None]:
    """Clean tables before/after each test."""
    await clean_database_tables()
    yield
    await clean_database_tables()
    await clean_database_tables()


async def _setup_base(
    cnpj: str, cpf_pac: str, cpf_med: str, email: str
) -> tuple[
    int,
    UUID,
    UUID,
    UUID,
]:
    """Create org, patient, doctor and attendance, returning ids."""
    async with async_session_factory() as session:
        org = make_organizacao(cnpj=cnpj)
        session.add(org)
        await session.commit()
        await session.refresh(org)
        paciente = make_paciente(org.id, cpf=cpf_pac)
        medico = make_profissional(
            org.id,
            cpf=cpf_med,
            email=email,
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
        return org.id, paciente.id, medico.id, atendimento.id


@pytest.mark.asyncio
async def test_salvar_evolucao_soap_service_commit_visivel_outra_sessao() -> None:
    """Service commit persists SOAP without router commit (separate session)."""
    org_id, _, medico_id, atend_id = await _setup_base(
        "11111111000111", "11111111111", "22222222211", "tx-soap@medisync.local"
    )
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
async def test_emitir_documento_service_commit_visivel_outra_sessao() -> None:
    """Service commit persists document+items without router commit."""
    org_id, _, medico_id, atend_id = await _setup_base(
        "22222222000111", "33333333311", "44444444411", "tx-doc@medisync.local"
    )
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
async def test_finalizar_consulta_service_commit_visivel_outra_sessao() -> None:
    """Service commit persists finalization (atendimento CONCLUIDO)."""
    org_id, _, medico_id, atend_id = await _setup_base(
        "33333333000111", "55555555511", "66666666611", "tx-fin@medisync.local"
    )
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
async def test_assinar_documento_service_commit_visivel_outra_sessao() -> None:
    """Service commit persists signature without router commit."""
    org_id, _, medico_id, atend_id = await _setup_base(
        "44444444000111", "77777777711", "88888888811", "tx-sign@medisync.local"
    )
    signer = AsyncMock()
    signer.assinar_pdf.return_value = b"%PDF-signed-bytes%"
    storage = AsyncMock()
    storage.obter_documento.return_value = b"%PDF-fake%"
    storage.salvar_documento.return_value = None

    doc_id: UUID
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
async def test_assinar_documento_outro_atendimento_404_signer_nao_chamado() -> None:
    """Ownership before PSC: wrong atendimento -> 404 and signer spy not called."""
    org_id, _, medico_id, atend_a = await _setup_base(
        "55555555000111", "99999999911", "00011122211", "tx-own@medisync.local"
    )
    async with async_session_factory() as s_setup:
        atendimento_b = make_atendimento(
            organizacao_id=org_id,
            paciente_id=(await _get_any_patient_id(org_id)),
            status="EM_ATENDIMENTO",
        )
        s_setup.add(atendimento_b)
        await s_setup.commit()
        await s_setup.refresh(atendimento_b)
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


async def _get_any_patient_id(org_id: int) -> UUID:
    """Return any patient id for org (used to create second attendance)."""
    from src.modules.identity.domain.models import Paciente

    async with async_session_factory() as session:
        res = await session.execute(
            select(Paciente.id).where(Paciente.organizacao_id == org_id).limit(1)
        )
        pid = res.scalar_one()
        assert isinstance(pid, UUID)
        return pid
