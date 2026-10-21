"""Clinical audit trail integration tests for queue and consultation (ADR-007).

Decisões: docs/adrs/ADR-007-Auditoria-Imutavel-Append-Only.md
Referência: docs/reference/audit/event-catalog.md
"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from src.core.audit.adapter import SqlAuditTrailAdapter
from src.core.audit.models import AtorPapel, AtorTipo
from src.core.audit.service import AuditService
from src.core.database import async_session_factory
from src.core.uuid7 import uuid7
from src.modules.consultation.application.dtos import (
    CriarItemPrescricaoDTO,
    EmitirDocumentoClinicoCommand,
    FinalizarConsultaCommand,
    RegistrarEvolucaoSOAPCommand,
)
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
)
from src.modules.consultation.application.services.evolucao_service import (
    EvolucaoService,
)
from src.modules.queue.application.dtos import AdmissaoAtendimentoCommand
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.models import PrioridadeClinica

from tests.doubles import (
    FakeICPBrasilSigner,
    FakeMemoryStorage,
    FakePDFGenerator,
    FakeValkey,
)
from tests.factories.identity import (
    make_organizacao,
    make_paciente,
)
from tests.factories.queue import make_atendimento
from tests.factories.scenarios import seed_clinical_scenario
from tests.helpers import clean_database_tables, make_pep_service

_SAMPLE_TCLE_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@dataclass
class DummyTriageEvaluation:
    prioridade_clinica: int
    alerta_samu_disparado: bool = False
    tcle_hash: str = ""
    tcle_texto: str = ""
    instrucao_redirecionamento: str | None = None


@pytest.fixture(autouse=True)
async def setup_clean_db() -> AsyncGenerator[None, None]:
    """Ensure clean tables before and after clinical audit integration tests."""
    await clean_database_tables()
    yield
    await clean_database_tables()


@pytest.mark.asyncio
async def test_admissao_paciente_records_audit_event_in_postgres() -> None:
    """Validate persistence of Atendimento and ADMISSAO_PACIENTE in PostgreSQL."""
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="10101010000199")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="10101010199")
        session.add(paciente)
        await session.commit()
        await session.refresh(paciente)

        fake_valkey = FakeValkey()
        mock_triage = AsyncMock()
        mock_triage.avaliar_risco = AsyncMock(
            return_value=DummyTriageEvaluation(
                prioridade_clinica=PrioridadeClinica.POUCO_URGENTE,
                alerta_samu_disparado=False,
                tcle_hash=_SAMPLE_TCLE_HASH,
                tcle_texto="Termo de Consentimento Livre e Esclarecido",
            )
        )
        mock_triage.registrar_triagem = AsyncMock(return_value=uuid7())

        fila_svc = FilaService(
            valkey=fake_valkey,  # type: ignore[reportArgumentType]
            db_session=session,
            alocacao_service=AsyncMock(spec=AlocacaoChamadaService),
            triage_port=mock_triage,
            audit_trail=SqlAuditTrailAdapter(session),
        )

        cmd = AdmissaoAtendimentoCommand(
            organizacao_id=org.id,
            paciente_id=paciente.id,
            queixa_principal="Cefaleia leve",
            sintomas=["cefaleia"],
            escala_dor=2,
            tcle_texto="Termo de Consentimento Livre e Esclarecido",
            tcle_hash=_SAMPLE_TCLE_HASH,
        )

        result = await fila_svc.admitir_paciente(cmd)
        atend_id = result.atendimento_id

    # Verify in separate session that both Atendimento and AuditEvent are committed
    async with async_session_factory() as verify_session:
        events = await AuditService.list_events_by_atendimento(
            verify_session,
            atendimento_id=atend_id,
        )
        assert len(events) == 1
        evt = events[0]
        assert evt.organizacao_id == org.id
        assert evt.atendimento_id == atend_id
        assert evt.tipo_evento == "ADMISSAO_PACIENTE"
        assert evt.ator_tipo == AtorTipo.PACIENTE
        assert evt.ator_papel == AtorPapel.PACIENTE
        assert evt.ator_id == paciente.id
        assert evt.tcle_hash == _SAMPLE_TCLE_HASH
        assert evt.payload["triagem_id"] == str(result.triagem_id)
        assert evt.payload["prioridade_clinica"] == PrioridadeClinica.POUCO_URGENTE


@pytest.mark.asyncio
async def test_rollback_reverts_audit_event_atomically() -> None:
    """Rollback reverts clinical entities and audit events (zero orphans)."""
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="20202020000199")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="20202020299")
        session.add(paciente)
        await session.commit()
        await session.refresh(paciente)

        atend = make_atendimento(org.id, paciente.id, tcle_hash=_SAMPLE_TCLE_HASH)
        session.add(atend)
        await session.flush()

        adapter = SqlAuditTrailAdapter(session)
        await adapter.record_event(
            organizacao_id=org.id,
            tipo_evento="ADMISSAO_PACIENTE",
            ator_tipo=AtorTipo.PACIENTE.value,
            ator_papel=AtorPapel.PACIENTE.value,
            ator_id=paciente.id,
            atendimento_id=atend.id,
            tcle_hash=_SAMPLE_TCLE_HASH,
            payload={"teste": "rollback"},
        )

        # Trigger explicit rollback
        await session.rollback()

        atend_id = atend.id

    # Verify zero records in separate session
    async with async_session_factory() as verify_session:
        events = await AuditService.list_events_by_atendimento(
            verify_session,
            atendimento_id=atend_id,
        )
        assert len(events) == 0


@pytest.mark.asyncio
async def test_pep_workflow_full_audit_trail_reconstruction() -> None:
    """Validate clinical audit trail reconstruction in chronological order."""
    async with async_session_factory() as session:
        cenario = await seed_clinical_scenario(
            session,
            org_cnpj="30303030000199",
            paciente_cpf="30303030399",
            medico_cpf="40404040499",
            medico_email="dr.audit.int@medisync.local",
            tcle_hash=_SAMPLE_TCLE_HASH,
        )
        atend_id = cenario.atendimento.id
        org_id = cenario.organizacao.id
        medico_id = cenario.medico.id

        pep_svc = make_pep_service(
            session,
            audit_trail=SqlAuditTrailAdapter(session),
            pdf_generator=FakePDFGenerator(),
            signer=FakeICPBrasilSigner(),
            storage=FakeMemoryStorage(),
        )

        # 1. Salvar Evolução SOAP
        cmd_soap = RegistrarEvolucaoSOAPCommand(
            atendimento_id=atend_id,
            organizacao_id=org_id,
            medico_id=medico_id,
            anamnese="Paciente com febre e cefaleia há 24h.",
            conduta="Prescrito sintomáticos e repouso.",
            cid10_principal="R50.9",
        )
        evolucao = await pep_svc.salvar_evolucao_soap(cmd_soap)
        assert evolucao.cid10_principal == "R50.9"

        # 2. Emitir Documento Clínico (Receita)
        cmd_doc = EmitirDocumentoClinicoCommand(
            atendimento_id=atend_id,
            organizacao_id=org_id,
            medico_id=medico_id,
            tipo_documento="RECEITA_SIMPLES",
            itens=[
                CriarItemPrescricaoDTO(
                    medicamento="Dipirona 500mg",
                    dosagem="500mg",
                    posologia="1 comprimido a cada 6h em caso de dor",
                    duracao="3 dias",
                )
            ],
        )
        doc = await pep_svc.emitir_documento(cmd_doc)
        assert doc.tipo_documento == "RECEITA_SIMPLES"

        # 3. Assinar Documento Clínico com ICP-Brasil
        creds = DoctorCertificateCredentials(token="fake-icp-brasil-token")
        assinado = await pep_svc.assinar_documento(
            documento_id=doc.id,
            atendimento_id=atend_id,
            credenciais=creds,
        )
        assert assinado.documento_id == doc.id

        # 4. Finalizar Consulta
        cmd_fim = FinalizarConsultaCommand(
            atendimento_id=atend_id,
            organizacao_id=org_id,
            medico_id=medico_id,
        )
        finalizada = await pep_svc.finalizar_consulta(cmd_fim)
        assert finalizada.is_finalizado is True

    # Reconstruct audit trail from separate session
    async with async_session_factory() as verify_session:
        events = await AuditService.list_events_by_atendimento(
            verify_session,
            atendimento_id=atend_id,
        )
        assert len(events) == 4

        # 1º evento: EVOLUCAO_SOAP_REGISTRADA
        evt1 = events[0]
        assert evt1.tipo_evento == "EVOLUCAO_SOAP_REGISTRADA"
        assert evt1.ator_tipo == AtorTipo.PROFISSIONAL
        assert evt1.ator_papel == AtorPapel.MEDICO
        assert evt1.ator_id == medico_id
        assert evt1.payload["cid10"] == "R50.9"
        assert evt1.payload["evolucao_id"] == str(evolucao.id)

        # 2º evento: DOCUMENTO_CLINICO_EMITIDO
        evt2 = events[1]
        assert evt2.tipo_evento == "DOCUMENTO_CLINICO_EMITIDO"
        assert evt2.ator_tipo == AtorTipo.PROFISSIONAL
        assert evt2.ator_papel == AtorPapel.MEDICO
        assert evt2.ator_id == medico_id
        assert evt2.payload["documento_id"] == str(doc.id)
        assert evt2.payload["tipo_documento"] == "RECEITA_SIMPLES"
        assert evt2.payload["itens_qtd"] == 1

        # 3º evento: DOCUMENTO_CLINICO_ASSINADO
        evt3 = events[2]
        assert evt3.tipo_evento == "DOCUMENTO_CLINICO_ASSINADO"
        assert evt3.ator_tipo == AtorTipo.PROFISSIONAL
        assert evt3.ator_papel == AtorPapel.MEDICO
        assert evt3.ator_id == medico_id
        assert evt3.payload["documento_id"] == str(doc.id)
        assert evt3.payload["tipo_documento"] == "RECEITA_SIMPLES"
        assert evt3.payload["sha256_hash"] == assinado.sha256_hash

        # 4º evento: CONSULTA_FINALIZADA
        evt4 = events[3]
        assert evt4.tipo_evento == "CONSULTA_FINALIZADA"
        assert evt4.ator_tipo == AtorTipo.PROFISSIONAL
        assert evt4.ator_papel == AtorPapel.MEDICO
        assert evt4.ator_id == medico_id
        assert evt4.estado_anterior == "EM_ATENDIMENTO"
        assert evt4.novo_estado == "CONCLUIDO"
        assert evt4.payload["evolucao_id"] == str(evolucao.id)

        # Chronological ordering check
        assert (
            evt1.registrado_em
            <= evt2.registrado_em
            <= evt3.registrado_em
            <= evt4.registrado_em
        )


@pytest.mark.asyncio
async def test_clinical_audit_event_immutability_trigger() -> None:
    """Clinical audit events are protected by append-only trigger."""
    async with async_session_factory() as session:
        cenario = await seed_clinical_scenario(
            session,
            org_cnpj="50505050000199",
            paciente_cpf="50505050599",
            medico_cpf="60606060699",
            medico_email="dr.immutability@medisync.local",
            tcle_hash=_SAMPLE_TCLE_HASH,
        )
        ev_svc = EvolucaoService(
            session=session,
            audit_trail=SqlAuditTrailAdapter(session),
        )
        cmd_soap = RegistrarEvolucaoSOAPCommand(
            atendimento_id=cenario.atendimento.id,
            organizacao_id=cenario.organizacao.id,
            medico_id=cenario.medico.id,
            anamnese="Queixa de dor de garganta.",
            conduta="Orientações gerais.",
            cid10_principal="J02.9",
        )
        await ev_svc.salvar_evolucao_soap(cmd_soap)

        # Retrieve the generated audit event
        events = await AuditService.list_events_by_atendimento(
            session,
            atendimento_id=cenario.atendimento.id,
        )
        assert len(events) == 1
        event_id = events[0].id

    # Attempt forbidden UPDATE
    async with async_session_factory() as evil_session:
        with pytest.raises(DBAPIError, match="append-only"):
            await evil_session.execute(
                text("UPDATE audit_events SET payload = '{}'::jsonb WHERE id = :id"),
                {"id": event_id},
            )
            await evil_session.commit()

    # Attempt forbidden DELETE
    async with async_session_factory() as evil_session:
        with pytest.raises(DBAPIError, match="append-only"):
            await evil_session.execute(
                text("DELETE FROM audit_events WHERE id = :id"),
                {"id": event_id},
            )
            await evil_session.commit()
