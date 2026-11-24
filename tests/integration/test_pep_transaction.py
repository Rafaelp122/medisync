"""Integration tests for PEP transaction ownership (service commits once)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_session_factory
from src.modules.consultation.application.dtos import (
    CriarItemPrescricaoDTO,
    EmitirDocumentoClinicoCommand,
    FinalizarConsultaCommand,
    RegistrarEvolucaoSOAPCommand,
)
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
)
from src.modules.consultation.application.ports.producao_ambulatorial_port import (
    ProducaoAmbulatorialPort,
)
from src.modules.consultation.domain.exceptions import (
    DocumentoClinicoNaoEncontradoError,
    TravaAntiFraudeAtestadoError,
)
from src.modules.consultation.domain.models import (
    DocumentoClinico,
    EvolucaoClinica,
    TipoDocumentoClinico,
)

from tests.doubles import FakeICPBrasilSigner, FakeMemoryStorage
from tests.factories.queue import make_atendimento
from tests.factories.scenarios import seed_clinical_scenario
from tests.helpers import make_documento_service, make_pep_service

pytestmark = pytest.mark.usefixtures("clean_db")


class _StaticFakeSigner(FakeICPBrasilSigner):
    """Named fake signer returning deterministic PDF bytes."""

    def __init__(self, payload: bytes) -> None:
        super().__init__()
        self._payload = payload

    async def assinar_pdf(
        self,
        pdf_bytes: bytes,
        credenciais: Any,
        metadata: Any = None,
    ) -> bytes:
        self.calls.append((pdf_bytes, credenciais, metadata))
        return self._payload


@pytest.mark.asyncio
async def test_salvar_evolucao_soap_service_commit_visivel_outra_sessao(
    db_session: AsyncSession,
) -> None:
    """Service commit persists SOAP without router commit (separate session)."""
    cenario = await seed_clinical_scenario(
        db_session,
        unidade_cnpj="11111111000111",
        paciente_cpf="11111111111",
        medico_cpf="22222222211",
        medico_email="tx-soap@medisync.local",
    )
    atend_id = cenario.atendimento.id
    medico_id = cenario.medico.id

    async with get_session_factory()() as s1:
        svc = make_pep_service(s1)
        cmd = RegistrarEvolucaoSOAPCommand(
            atendimento_id=atend_id,
            medico_id=medico_id,
            anamnese="Queixa de tosse há 2 dias.",
            conduta="Hidratação e sintomáticos.",
            exame_fisico_virtual="Bom estado geral.",
            cid10_principal="J00",
        )
        await svc.salvar_evolucao_soap(cmd)

    async with get_session_factory()() as s2:
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
        unidade_cnpj="22222222000111",
        paciente_cpf="33333333311",
        medico_cpf="44444444411",
        medico_email="tx-doc@medisync.local",
    )
    atend_id = cenario.atendimento.id
    medico_id = cenario.medico.id

    async with get_session_factory()() as s1:
        pep_svc = make_pep_service(s1)
        doc_svc = make_documento_service(s1)
        await pep_svc.salvar_evolucao_soap(
            RegistrarEvolucaoSOAPCommand(
                atendimento_id=atend_id,
                medico_id=medico_id,
                anamnese="Dor aguda.",
                conduta="Analgesia.",
                identidade_verificada=True,
            )
        )
        cmd = EmitirDocumentoClinicoCommand(
            atendimento_id=atend_id,
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
        doc = await doc_svc.emitir_documento(cmd)
        doc_id = doc.id

    async with get_session_factory()() as s2:
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
    """Service commit persists finalization (CONCLUIDO) with savepoint safety."""
    cenario = await seed_clinical_scenario(
        db_session,
        unidade_cnpj="33333333000111",
        paciente_cpf="55555555511",
        medico_cpf="66666666611",
        medico_email="tx-fin@medisync.local",
    )
    atend_id = cenario.atendimento.id
    medico_id = cenario.medico.id

    async with get_session_factory()() as s1:
        svc = make_pep_service(s1)
        await svc.salvar_evolucao_soap(
            RegistrarEvolucaoSOAPCommand(
                atendimento_id=atend_id,
                medico_id=medico_id,
                anamnese="Cefaleia leve.",
                conduta="Sintomático e repouso.",
                identidade_verificada=True,
            )
        )

    class _PostgresFailingProducao(ProducaoAmbulatorialPort):
        async def consolidar_teleconsulta(
            self,
            *,
            atendimento_id: UUID,
            profissional_id: UUID,
            paciente_id: UUID,
            cnes: str | None = None,
            codigo_sigtap: str = "03.01.01.025-0",
            carater_atendimento: str = "02",
        ) -> None:
            # Simula SQL quebrada dentro do savepoint sem quebrar transação externa
            await s1b.execute(text("SELECT 1 / 0"))

    async with get_session_factory()() as s1b:
        svc = make_pep_service(s1b, producao_port=_PostgresFailingProducao())
        result = await svc.finalizar_consulta(
            FinalizarConsultaCommand(
                atendimento_id=atend_id,
                medico_id=medico_id,
            )
        )
        assert result.is_finalizado is True

    async with get_session_factory()() as s2:
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
        unidade_cnpj="44444444000111",
        paciente_cpf="77777777711",
        medico_cpf="88888888811",
        medico_email="tx-sign@medisync.local",
    )
    atend_id = cenario.atendimento.id
    medico_id = cenario.medico.id

    signer = _StaticFakeSigner(b"%PDF-signed-bytes%")
    storage = FakeMemoryStorage()

    async with get_session_factory()() as s1:
        pep_svc = make_pep_service(s1, storage=storage)
        doc_svc = make_documento_service(s1, signer=signer, storage=storage)
        await pep_svc.salvar_evolucao_soap(
            RegistrarEvolucaoSOAPCommand(
                atendimento_id=atend_id,
                medico_id=medico_id,
                anamnese="Odinofagia.",
                conduta="Dipirona.",
                identidade_verificada=True,
            )
        )
        doc = await doc_svc.emitir_documento(
            EmitirDocumentoClinicoCommand(
                atendimento_id=atend_id,
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

    async with get_session_factory()() as s1b:
        doc_svc_b = make_documento_service(s1b, signer=signer, storage=storage)
        creds = DoctorCertificateCredentials(
            token="valid-token", provider="fake", certificate_alias="cert-tx"
        )
        result = await doc_svc_b.assinar(doc_id, atend_id, creds)
        assert result.tamanho_bytes == len(b"%PDF-signed-bytes%")
        assert result.sha256_hash is not None

    async with get_session_factory()() as s2:
        res = await s2.execute(
            select(DocumentoClinico).where(DocumentoClinico.id == doc_id)
        )
        persisted = res.scalar_one_or_none()
        assert persisted is not None
        assert persisted.chave_s3.startswith(f"consultations/{atend_id}/documents/")
        assert persisted.assinado_em is not None
        assert persisted.sha256_hash is not None
        assert len(persisted.sha256_hash) == 64


@pytest.mark.asyncio
async def test_assinar_documento_outro_atendimento_404_signer_nao_chamado(
    db_session: AsyncSession,
) -> None:
    """Ownership before PSC: wrong atendimento -> 404 and signer spy not called."""
    cenario = await seed_clinical_scenario(
        db_session,
        unidade_cnpj="55555555000111",
        paciente_cpf="99999999911",
        medico_cpf="00011122211",
        medico_email="tx-own@medisync.local",
    )
    atend_a = cenario.atendimento.id
    medico_id = cenario.medico.id

    atendimento_b = make_atendimento(
        paciente_id=cenario.paciente.id,
        status="EM_ATENDIMENTO",
    )
    db_session.add(atendimento_b)
    await db_session.commit()
    await db_session.refresh(atendimento_b)
    atend_b = atendimento_b.id

    signer_spy = _StaticFakeSigner(b"%PDF-should-not-happen%")
    storage = FakeMemoryStorage()

    async with get_session_factory()() as s1:
        pep_svc = make_pep_service(s1, storage=storage)
        doc_svc = make_documento_service(s1, signer=signer_spy, storage=storage)
        await pep_svc.salvar_evolucao_soap(
            RegistrarEvolucaoSOAPCommand(
                atendimento_id=atend_a,
                medico_id=medico_id,
                anamnese="Cefaleia.",
                conduta="Paracetamol.",
                identidade_verificada=True,
            )
        )
        doc = await doc_svc.emitir_documento(
            EmitirDocumentoClinicoCommand(
                atendimento_id=atend_a,
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

    async with get_session_factory()() as s2:
        doc_svc2 = make_documento_service(s2, signer=signer_spy, storage=storage)
        creds = DoctorCertificateCredentials(token="tok", provider="fake")
        with pytest.raises(DocumentoClinicoNaoEncontradoError):
            await doc_svc2.assinar(doc_id, atend_b, creds)

    assert signer_spy.calls == []

    async with get_session_factory()() as s3:
        res = await s3.execute(
            select(DocumentoClinico).where(DocumentoClinico.id == doc_id)
        )
        persisted = res.scalar_one_or_none()
        assert persisted is not None
        assert persisted.sha256_hash == original_hash


@pytest.mark.asyncio
async def test_rn09_trava_180s_usa_chamada_iniciada_em_real_em_postgres(
    db_session: AsyncSession,
) -> None:
    """RN09 Postgres: criado_em 10min ago + chamada_iniciada_em 20s ago -> blocked."""
    now = datetime.now(UTC)
    cenario = await seed_clinical_scenario(
        db_session,
        unidade_cnpj="66666666000111",
        paciente_cpf="66666666611",
        medico_cpf="77777777722",
        medico_email="rn09-int@medisync.local",
    )
    atend_id = cenario.atendimento.id
    medico_id = cenario.medico.id

    await db_session.execute(
        text(
            "UPDATE atendimentos SET criado_em = :criado, "
            "chamada_iniciada_em = :chamada WHERE id = :id"
        ),
        {
            "criado": now - timedelta(minutes=10),
            "chamada": now - timedelta(seconds=20),
            "id": atend_id,
        },
    )
    await db_session.commit()

    async with get_session_factory()() as s1:
        pep_svc = make_pep_service(s1)
        doc_svc = make_documento_service(s1)
        await pep_svc.salvar_evolucao_soap(
            RegistrarEvolucaoSOAPCommand(
                atendimento_id=atend_id,
                medico_id=medico_id,
                anamnese="Sintomas gripais",
                conduta="Atestado",
                identidade_verificada=True,
            )
        )
        with pytest.raises(TravaAntiFraudeAtestadoError):
            await doc_svc.emitir_documento(
                EmitirDocumentoClinicoCommand(
                    atendimento_id=atend_id,
                    medico_id=medico_id,
                    tipo_documento=TipoDocumentoClinico.ATESTADO_MEDICO,
                )
            )
