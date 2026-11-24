"""Unit tests for deep PEPService: SOAP, ClinicalPdfCompiler and single commit."""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

import pytest
from src.core.uuid7 import uuid7
from src.modules.consultation.application.dtos import (
    FinalizarConsultaCommand,
    HistoricoAtendimentoItemDTO,
    PacienteDocumentoItemDTO,
    RegistrarEvolucaoSOAPCommand,
)
from src.modules.consultation.application.policies.clinical_access_policy import (
    ClinicalAccessPolicy,
)
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoHistoricoDTO,
    AtendimentoReaderPort,
    AtendimentoResumoDTO,
    HistoricoAtendimentoReaderPort,
    is_atendimento_terminal,
)
from src.modules.consultation.application.ports.producao_ambulatorial_port import (
    ProducaoAmbulatorialPort,
)
from src.modules.consultation.application.services.clinical_pdf_compiler import (
    ClinicalPdfCompiler,
)
from src.modules.consultation.application.services.pep_service import PEPService
from src.modules.consultation.composition import (
    QueueStoreAtendimentoReaderAdapter,
    build_pep_service_for_session,
)
from src.modules.consultation.domain.exceptions import (
    ConsultaFinalizadaError,
    ConsultaInvalidaError,
    DocumentoClinicoNaoEncontradoError,
    EvolucaoNaoEncontradaError,
)
from src.modules.consultation.domain.models import (
    DocumentoClinico,
    EvolucaoClinica,
    TipoDocumentoClinico,
)
from src.modules.queue.application.ports.queue_store_port import AtendimentoSnapshotDTO

from tests.doubles import (
    FakeAsyncSession,
    FakeAtendimentoReader,
    FakeAuditTrail,
    FakeDocumentDirectory,
    FakeMemoryStorage,
    FakePDFGenerator,
    FakeProducaoAmbulatorialPort,
    FakeResult,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _build_test_pep_service(
    session: FakeAsyncSession,
    *,
    atendimento_reader: AtendimentoReaderPort | None = None,
    producao_port: ProducaoAmbulatorialPort | None = None,
    pdf_generator: FakePDFGenerator | None = None,
    storage: FakeMemoryStorage | None = None,
    audit_trail: FakeAuditTrail | None = None,
) -> PEPService:
    typed_session = cast("AsyncSession", session)
    compiler = ClinicalPdfCompiler(
        session=typed_session,
        pdf_generator=pdf_generator or FakePDFGenerator(),
        storage=storage or FakeMemoryStorage(),
        directory=FakeDocumentDirectory(),
    )
    return PEPService(
        session=typed_session,
        pdf_compiler=compiler,
        atendimento_reader=atendimento_reader,
        audit_trail=audit_trail,
        producao_port=producao_port,
    )


@pytest.mark.asyncio
async def test_pep_service_compilar_pdf_e_bloqueio_idor() -> None:
    """compilar_pdf enforces atendimento_id ownership via ClinicalPdfCompiler."""
    atend_a = uuid7()
    atend_b = uuid7()
    med_id = uuid7()
    doc_id = uuid7()
    doc = DocumentoClinico(
        id=doc_id,
        atendimento_id=atend_a,
        medico_id=med_id,
        tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
        chave_s3=f"consultations/{atend_a}/documents/{doc_id}.pdf",
    )
    storage = FakeMemoryStorage()
    pdf_gen = FakePDFGenerator(content=b"%PDF-compiled-real%")
    session = FakeAsyncSession(results=[FakeResult(doc), FakeResult(None)])
    svc = _build_test_pep_service(session, pdf_generator=pdf_gen, storage=storage)

    pdf_bytes = await svc.compilar_pdf(doc_id, atendimento_id=atend_a)
    assert pdf_bytes == b"%PDF-compiled-real%"

    # Mismatch atendimento_id raises 404 (IDOR protection)
    session_idor = FakeAsyncSession(results=[FakeResult(doc)])
    svc_idor = _build_test_pep_service(
        session_idor, pdf_generator=pdf_gen, storage=storage
    )
    with pytest.raises(DocumentoClinicoNaoEncontradoError):
        await svc_idor.compilar_pdf(doc_id, atendimento_id=atend_b)


@pytest.mark.asyncio
async def test_pep_service_salvar_e_obter_evolucao_absorvidos() -> None:
    """PEPService persists and loads EvolucaoClinica without EvolucaoService."""
    atend_id = uuid7()
    med_id = uuid7()
    session = FakeAsyncSession(results=[FakeResult(None)])
    reader = FakeAtendimentoReader(
        resumo=AtendimentoResumoDTO(
            atendimento_id=atend_id,
            medico_id=med_id,
            status="EM_ATENDIMENTO",
            tcle_hash="a" * 64,
            is_terminal=False,
        )
    )
    svc = _build_test_pep_service(session, atendimento_reader=reader)
    cmd = RegistrarEvolucaoSOAPCommand(
        atendimento_id=atend_id,
        medico_id=med_id,
        anamnese="Paciente com febre",
        conduta="Prescrito paracetamol",
        codigo_sigtap="03.01.01.004-8",
    )

    saved = await svc.salvar_evolucao_soap(cmd)
    assert saved.atendimento_id == atend_id
    assert saved.codigo_sigtap == "03.01.01.004-8"
    assert session.commits == 1

    # Updating with blank codigo_sigtap preserves existing code (Lean fix)
    session_update = FakeAsyncSession(results=[FakeResult(saved)])
    svc_update = _build_test_pep_service(session_update, atendimento_reader=reader)
    updated = await svc_update.salvar_evolucao_soap(
        RegistrarEvolucaoSOAPCommand(
            atendimento_id=atend_id,
            medico_id=med_id,
            anamnese="Febre controlada",
            conduta="Manter hidratacao",
            codigo_sigtap="   ",
        )
    )
    assert updated.codigo_sigtap == "03.01.01.004-8"

    session_get = FakeAsyncSession(results=[FakeResult(saved)])
    svc_get = _build_test_pep_service(session_get, atendimento_reader=reader)
    retrieved = await svc_get.obter_evolucao(atend_id)
    assert retrieved.id == saved.id

    session_missing = FakeAsyncSession(results=[FakeResult(None)])
    svc_missing = _build_test_pep_service(session_missing)
    with pytest.raises(EvolucaoNaoEncontradaError):
        await svc_missing.obter_evolucao(atend_id)


@pytest.mark.asyncio
async def test_pep_service_salvar_bloqueia_quando_atendimento_terminal() -> None:
    """Ported from test_evolucao_service: terminal attendance blocks SOAP edits."""
    atend_id = uuid7()
    med_id = uuid7()
    session = FakeAsyncSession(results=[FakeResult(None)])
    reader = FakeAtendimentoReader(
        resumo=AtendimentoResumoDTO(
            atendimento_id=atend_id,
            medico_id=med_id,
            status="CONCLUIDO",
            tcle_hash="a" * 64,
            is_terminal=True,
        )
    )
    svc = _build_test_pep_service(session, atendimento_reader=reader)
    cmd = RegistrarEvolucaoSOAPCommand(
        atendimento_id=atend_id,
        medico_id=med_id,
        anamnese="a",
        conduta="c",
    )
    with pytest.raises(ConsultaFinalizadaError):
        await svc.salvar_evolucao_soap(cmd)


@pytest.mark.asyncio
async def test_pep_service_unified_is_terminal() -> None:
    """_is_terminal checks terminal state via unified reader."""
    atend_id = uuid7()
    reader = FakeAtendimentoReader(
        resumo=AtendimentoResumoDTO(
            atendimento_id=atend_id,
            medico_id=uuid7(),
            status="CONCLUIDO",
            tcle_hash="x" * 64,
            is_terminal=True,
        )
    )
    svc = _build_test_pep_service(FakeAsyncSession(), atendimento_reader=reader)
    assert await svc._is_terminal(atend_id) is True  # pyright: ignore[reportPrivateUsage]

    reader.resumo = AtendimentoResumoDTO(
        atendimento_id=atend_id,
        medico_id=uuid7(),
        status="EM_ATENDIMENTO",
        tcle_hash="x" * 64,
        is_terminal=False,
    )
    assert await svc._is_terminal(atend_id) is False  # pyright: ignore[reportPrivateUsage]

    reader.resumo = None
    assert await svc._is_terminal(atend_id) is False  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_is_atendimento_terminal_helper_handles_none_and_error() -> None:
    """is_atendimento_terminal returns False safely if reader is None or raises."""
    assert await is_atendimento_terminal(None, uuid4()) is False

    failing_reader = FakeAtendimentoReader(error_obter_resumo=RuntimeError("db down"))
    assert await is_atendimento_terminal(failing_reader, uuid4()) is False


def test_build_pep_service_for_session_wires_deep_pep() -> None:
    """build_pep_service_for_session wires ClinicalPdfCompiler without Signer."""
    session = cast("AsyncSession", FakeAsyncSession())
    svc = build_pep_service_for_session(session=session)
    assert isinstance(svc, PEPService)
    assert isinstance(svc._pdf_compiler, ClinicalPdfCompiler)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(svc.atendimento_reader, AtendimentoReaderPort)
    assert isinstance(svc.atendimento_reader, HistoricoAtendimentoReaderPort)
    assert svc.producao_port is not None
    assert not hasattr(svc, "evolucao_service")
    assert not hasattr(svc, "documento_service")


def test_pep_service_has_no_raw_sql_text_or_cross_module_table_queries() -> None:
    """PEPService must never import sqlalchemy.text or run raw cross-module SQL."""
    import ast
    from pathlib import Path

    pep_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "modules"
        / "consultation"
        / "application"
        / "services"
        / "pep_service.py"
    )
    source = pep_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(pep_path))

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "") == "sqlalchemy":
            imported = {alias.name for alias in node.names}
            assert "text" not in imported, "PEPService must not import sqlalchemy.text"
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "text":
                raise AssertionError("PEPService must not call sqlalchemy.text()")

    lowered = source.lower()
    assert "from atendimentos" not in lowered
    assert "join triagens" not in lowered


@pytest.mark.asyncio
async def test_pep_service_finalizar_consulta_dispara_consolidacao_ambulatorial() -> (
    None
):
    """finalizar_consulta triggers ambulatory BPA-I consolidation with 1 commit."""
    atend_id = uuid4()
    medico_id = uuid4()
    paciente_id = uuid4()

    evolucao = EvolucaoClinica(
        atendimento_id=atend_id,
        medico_id=medico_id,
        anamnese="Paciente com tosse",
        conduta="Prescrito xarope",
        codigo_sigtap="03.01.01.025-0",
        identidade_verificada=True,
    )

    fake_session = FakeAsyncSession(results=[FakeResult(evolucao), FakeResult([])])
    resumo = AtendimentoResumoDTO(
        atendimento_id=atend_id,
        medico_id=medico_id,
        paciente_id=paciente_id,
        status="EM_ATENDIMENTO",
        tcle_hash="h" * 64,
        is_terminal=False,
    )
    fake_reader = FakeAtendimentoReader(resumo=resumo)
    fake_producao = FakeProducaoAmbulatorialPort()

    svc = _build_test_pep_service(
        fake_session,
        atendimento_reader=fake_reader,
        producao_port=fake_producao,
    )

    cmd = FinalizarConsultaCommand(
        atendimento_id=atend_id,
        medico_id=medico_id,
    )

    result = await svc.finalizar_consulta(cmd)

    assert result.atendimento_id == atend_id
    assert result.is_finalizado is True
    assert fake_session.commits == 1
    assert len(fake_reader.obter_resumo_calls) == 1

    assert len(fake_producao.consolidacoes) == 1
    consolidacao = fake_producao.consolidacoes[0]
    assert consolidacao["atendimento_id"] == atend_id
    assert consolidacao["profissional_id"] == medico_id
    assert consolidacao["paciente_id"] == paciente_id
    assert consolidacao["codigo_sigtap"] == "03.01.01.025-0"


@pytest.mark.asyncio
async def test_pep_service_finalizar_consulta_savepoint_rollback() -> None:
    """Ambulatory failure rolls back savepoint without partial add or commit failure."""
    atend_id = uuid4()
    medico_id = uuid4()
    paciente_id = uuid4()

    evolucao = EvolucaoClinica(
        atendimento_id=atend_id,
        medico_id=medico_id,
        anamnese="Paciente com febre",
        conduta="Prescrito antitermico",
        codigo_sigtap="03.01.01.025-0",
        identidade_verificada=True,
    )

    fake_session = FakeAsyncSession(results=[FakeResult(evolucao), FakeResult([])])
    resumo = AtendimentoResumoDTO(
        atendimento_id=atend_id,
        medico_id=medico_id,
        paciente_id=paciente_id,
        status="EM_ATENDIMENTO",
        tcle_hash="h" * 64,
        is_terminal=False,
    )
    fake_reader = FakeAtendimentoReader(resumo=resumo)

    class _PartialWriteFailingProducao(ProducaoAmbulatorialPort):
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
            fake_session.add({"partial_bpa": atendimento_id})
            raise RuntimeError("BPA-I service error")

    svc = _build_test_pep_service(
        fake_session,
        atendimento_reader=fake_reader,
        producao_port=_PartialWriteFailingProducao(),
    )

    result = await svc.finalizar_consulta(
        FinalizarConsultaCommand(atendimento_id=atend_id, medico_id=medico_id)
    )
    assert result.is_finalizado is True
    assert fake_session.savepoint_rollbacks == 1
    assert fake_session.added == []
    assert fake_session.commits == 1


@pytest.mark.asyncio
async def test_clinical_access_plus_finalize_executes_single_queue_store_read() -> None:
    """Shared QueueStoreAtendimentoReaderAdapter caches resumo across policy and PEP."""
    atend_id = uuid7()
    medico_id = uuid7()
    paciente_id = uuid7()
    now = datetime.now(UTC)

    snapshot = AtendimentoSnapshotDTO(
        id=atend_id,
        paciente_id=paciente_id,
        medico_id=medico_id,
        status="EM_ATENDIMENTO",
        prioridade_clinica=3,
        tcle_hash="h" * 64,
        data_entrada_fila=now,
        criado_em=now,
        is_terminal=False,
        chamada_iniciada_em=now,
    )

    class _CountingQueueStore:
        def __init__(self) -> None:
            self.buscar_calls = 0

        async def buscar_atendimento(
            self, atendimento_id: UUID
        ) -> AtendimentoSnapshotDTO | None:
            self.buscar_calls += 1
            return snapshot if atendimento_id == snapshot.id else None

        async def concluir_atendimento(
            self, atendimento_id: UUID, *, auto_commit: bool = True
        ) -> UUID | None:
            return medico_id

        async def liberar_consulta_ativa_medico(self, medico_id_arg: UUID) -> None:
            return None

        async def atender_chamada(self, atendimento_id: UUID) -> None:
            return None

        async def listar_historico_paciente(self, paciente_id_arg: UUID) -> list[Any]:
            return []

    store = _CountingQueueStore()
    adapter = QueueStoreAtendimentoReaderAdapter(store)  # pyright: ignore[reportArgumentType]

    resumo_policy = await ClinicalAccessPolicy.validar_acesso_clinico(
        atendimento_id=atend_id,
        medico_id=medico_id,
        reader=adapter,
        is_mutation=True,
    )
    assert resumo_policy.atendimento_id == atend_id

    evolucao = EvolucaoClinica(
        atendimento_id=atend_id,
        medico_id=medico_id,
        anamnese="Anamnese",
        conduta="Conduta",
        identidade_verificada=True,
    )
    fake_session = FakeAsyncSession(results=[FakeResult(evolucao), FakeResult([])])
    svc = _build_test_pep_service(fake_session, atendimento_reader=adapter)
    await svc.finalizar_consulta(
        FinalizarConsultaCommand(atendimento_id=atend_id, medico_id=medico_id)
    )
    assert store.buscar_calls == 1


@pytest.mark.asyncio
async def test_pep_warning_on_reader_obter_resumo_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    atend_id = uuid4()
    medico_id = uuid4()

    evolucao = EvolucaoClinica(
        atendimento_id=atend_id,
        medico_id=medico_id,
        anamnese="Paciente com dor",
        conduta="Orientação médica",
        identidade_verificada=True,
    )
    fake_session = FakeAsyncSession(results=[FakeResult(evolucao), FakeResult([])])
    fake_reader = FakeAtendimentoReader(
        error_obter_resumo=RuntimeError("Reader timeout error")
    )
    svc = _build_test_pep_service(
        session=fake_session,
        atendimento_reader=fake_reader,
    )
    cmd = FinalizarConsultaCommand(
        atendimento_id=atend_id,
        medico_id=medico_id,
    )

    with caplog.at_level(logging.WARNING):
        result = await svc.finalizar_consulta(cmd)

    assert result.is_finalizado is True
    assert fake_session.commits == 1
    assert "Falha ao obter resumo do atendimento" in caplog.text
    assert str(atend_id) in caplog.text
    assert "Reader timeout error" in caplog.text


@pytest.mark.asyncio
async def test_pep_warning_on_reader_concluir_atendimento_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    atend_id = uuid4()
    medico_id = uuid4()
    paciente_id = uuid4()

    evolucao = EvolucaoClinica(
        atendimento_id=atend_id,
        medico_id=medico_id,
        anamnese="Paciente com febre",
        conduta="Prescrição",
        identidade_verificada=True,
    )
    fake_session = FakeAsyncSession(results=[FakeResult(evolucao), FakeResult([])])
    resumo = AtendimentoResumoDTO(
        atendimento_id=atend_id,
        medico_id=medico_id,
        paciente_id=paciente_id,
        status="EM_ATENDIMENTO",
        tcle_hash="h" * 64,
        is_terminal=False,
    )
    fake_reader = FakeAtendimentoReader(
        resumo=resumo,
        error_concluir_atendimento=RuntimeError("Queue store failure"),
    )
    svc = _build_test_pep_service(
        session=fake_session,
        atendimento_reader=fake_reader,
    )
    cmd = FinalizarConsultaCommand(
        atendimento_id=atend_id,
        medico_id=medico_id,
    )

    with caplog.at_level(logging.WARNING):
        result = await svc.finalizar_consulta(cmd)

    assert result.is_finalizado is True
    assert fake_session.commits == 1
    assert "Falha ao concluir atendimento" in caplog.text
    assert str(atend_id) in caplog.text
    assert "Queue store failure" in caplog.text


@pytest.mark.asyncio
async def test_pep_finalizar_consulta_transacao_unica_e_libera_lock_pos_commit() -> (
    None
):
    """finalizar_consulta uses auto_commit=False, commits 1x, and frees doctor lock."""
    atend_id = uuid4()
    medico_id = uuid4()
    paciente_id = uuid4()

    evolucao = EvolucaoClinica(
        atendimento_id=atend_id,
        medico_id=medico_id,
        anamnese="Quadro clínico estável",
        conduta="Alta com orientações",
        identidade_verificada=True,
    )
    fake_session = FakeAsyncSession(results=[FakeResult(evolucao), FakeResult([])])
    resumo = AtendimentoResumoDTO(
        atendimento_id=atend_id,
        medico_id=medico_id,
        paciente_id=paciente_id,
        status="EM_ATENDIMENTO",
        tcle_hash="h" * 64,
        is_terminal=False,
    )
    fake_reader = FakeAtendimentoReader(resumo=resumo)
    svc = _build_test_pep_service(
        session=fake_session,
        atendimento_reader=fake_reader,
    )
    result = await svc.finalizar_consulta(
        FinalizarConsultaCommand(atendimento_id=atend_id, medico_id=medico_id)
    )

    assert result.is_finalizado is True
    assert fake_reader.atendimento_concluido is True
    assert fake_reader.last_auto_commit is False
    assert fake_session.commits == 1
    assert fake_reader.liberados_consulta == [medico_id]


@pytest.mark.asyncio
async def test_pep_warning_on_producao_failure_with_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    atend_id = uuid4()
    medico_id = uuid4()
    paciente_id = uuid4()

    evolucao = EvolucaoClinica(
        atendimento_id=atend_id,
        medico_id=medico_id,
        anamnese="Paciente com tosse",
        conduta="Xarope",
        codigo_sigtap="03.01.01.025-0",
        identidade_verificada=True,
    )
    fake_session = FakeAsyncSession(results=[FakeResult(evolucao), FakeResult([])])
    resumo = AtendimentoResumoDTO(
        atendimento_id=atend_id,
        medico_id=medico_id,
        paciente_id=paciente_id,
        status="EM_ATENDIMENTO",
        tcle_hash="h" * 64,
        is_terminal=False,
    )
    fake_reader = FakeAtendimentoReader(resumo=resumo)
    failing_producao = FakeProducaoAmbulatorialPort(
        error=RuntimeError("BPA-I service timeout")
    )
    svc = _build_test_pep_service(
        session=fake_session,
        atendimento_reader=fake_reader,
        producao_port=failing_producao,
    )
    cmd = FinalizarConsultaCommand(
        atendimento_id=atend_id,
        medico_id=medico_id,
    )

    with caplog.at_level(logging.WARNING):
        result = await svc.finalizar_consulta(cmd)

    assert result.is_finalizado is True
    assert fake_session.commits == 1
    assert "Falha ao consolidar teleconsulta" in caplog.text
    assert str(atend_id) in caplog.text
    assert str(medico_id) in caplog.text
    assert str(paciente_id) in caplog.text
    assert "03.01.01.025-0" in caplog.text
    assert "BPA-I service timeout" in caplog.text


@pytest.mark.asyncio
async def test_finalizar_consulta_bloqueia_sem_identidade_verificada_cfm() -> None:
    """CFM 2.314/2022 forbids finalizing consultation without identity verification."""
    atend_id = uuid4()
    medico_id = uuid4()
    evolucao = EvolucaoClinica(
        atendimento_id=atend_id,
        medico_id=medico_id,
        anamnese="Cefaleia",
        conduta="Analgesico",
        identidade_verificada=False,
    )
    svc = _build_test_pep_service(session=FakeAsyncSession([FakeResult(evolucao)]))

    with pytest.raises(ConsultaInvalidaError, match="identidade_verificada=False"):
        await svc.finalizar_consulta(
            FinalizarConsultaCommand(
                atendimento_id=atend_id,
                medico_id=medico_id,
            )
        )


@pytest.mark.asyncio
async def test_pep_service_patient_portal_empty_history_and_uuid7_docs() -> None:
    """Empty patient history skips DB queries and UUIDv7 docs extract criado_em."""
    paciente_id_val = uuid7()
    medico_id = uuid7()
    atend_id = uuid7()

    class _EmptyReader:
        async def obter_resumo(
            self, atendimento_id: object
        ) -> AtendimentoResumoDTO | None:
            return None

        async def concluir_atendimento(
            self,
            atendimento_id: object,
            *,
            auto_commit: bool = True,
        ) -> None:
            return None

        async def liberar_consulta_ativa_medico(self, medico_id: object) -> None:
            return None

        async def atender_chamada(self, atendimento_id: object) -> None:
            return None

        async def listar_historico_paciente(
            self, paciente_id: object
        ) -> list[AtendimentoHistoricoDTO]:
            return []

    fake_session_empty = FakeAsyncSession()
    svc_empty = _build_test_pep_service(
        session=fake_session_empty,
        atendimento_reader=_EmptyReader(),  # pyright: ignore[reportArgumentType]
    )
    assert await svc_empty.listar_historico_paciente(paciente_id_val) == []
    assert await svc_empty.listar_documentos_paciente(paciente_id_val) == []
    assert fake_session_empty.executes == 0

    class _OneReader(_EmptyReader):
        async def listar_historico_paciente(
            self, paciente_id: object
        ) -> list[AtendimentoHistoricoDTO]:
            return [
                AtendimentoHistoricoDTO(
                    atendimento_id=atend_id,
                    paciente_id=paciente_id_val,
                    status="CONCLUIDO",
                    prioridade_clinica=3,
                    criado_em=datetime.now(UTC),
                )
            ]

    doc = DocumentoClinico(
        id=uuid7(),
        atendimento_id=atend_id,
        medico_id=medico_id,
        tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
        chave_s3="consultations/doc.pdf",
    )
    fake_session_doc = FakeAsyncSession(results=[FakeResult([doc])])
    svc_doc = _build_test_pep_service(
        session=fake_session_doc,
        atendimento_reader=_OneReader(),  # pyright: ignore[reportArgumentType]
    )
    docs = await svc_doc.listar_documentos_paciente(paciente_id_val)
    assert len(docs) == 1
    assert isinstance(docs[0], PacienteDocumentoItemDTO)
    assert docs[0].status_assinatura == "EMITIDO"
    assert docs[0].criado_em is not None
    assert isinstance(
        HistoricoAtendimentoItemDTO(
            atendimento_id=atend_id,
            status="CONCLUIDO",
            prioridade_clinica=3,
            queixa_principal=None,
            criado_em=datetime.now(UTC),
            finalizado_em=None,
            medico_id=None,
        ),
        HistoricoAtendimentoItemDTO,
    )
