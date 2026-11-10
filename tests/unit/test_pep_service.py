"""Unit tests for PEPService: single facade, compilar_pdf, assinar_documento."""

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.modules.consultation.application.dtos import (
    DocumentoAssinadoResult,
    FinalizarConsultaCommand,
    RegistrarEvolucaoSOAPCommand,
)
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoReaderPort,
    AtendimentoResumoDTO,
    is_atendimento_terminal,
)
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
    ICPBrasilSignerPort,
)
from src.modules.consultation.application.ports.pdf_generator_port import (
    PDFGeneratorPort,
)
from src.modules.consultation.application.ports.storage_port import StoragePort
from src.modules.consultation.application.services.documento_service import (
    DocumentoService,
)
from src.modules.consultation.application.services.evolucao_service import (
    EvolucaoService,
)
from src.modules.consultation.application.services.pep_service import PEPService
from src.modules.consultation.composition import build_pep_service_for_session
from src.modules.consultation.domain.models import EvolucaoClinica
from src.modules.consultation.infrastructure.memory_signed_cache import (
    MemorySignedCache,
)

from tests.doubles import (
    FakeAsyncSession,
    FakeAtendimentoReader,
    FakeICPBrasilSigner,
    FakeMemoryStorage,
    FakePDFGenerator,
    FakeProducaoAmbulatorialPort,
    FakeResult,
)


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_pdf_generator() -> MagicMock:
    return MagicMock(spec=PDFGeneratorPort)


@pytest.fixture
def mock_signer() -> AsyncMock:
    return AsyncMock(spec=ICPBrasilSignerPort)


@pytest.fixture
def mock_storage() -> AsyncMock:
    return AsyncMock(spec=StoragePort)


@pytest.fixture
def mock_documento_service() -> AsyncMock:
    return AsyncMock(spec=DocumentoService)


@pytest.fixture
def mock_atendimento_reader() -> AsyncMock:
    reader = AsyncMock(spec=AtendimentoReaderPort)
    reader.obter_resumo.return_value = None
    return reader


@pytest.fixture
def mock_evolucao_service() -> AsyncMock:
    return AsyncMock(spec=EvolucaoService)


@pytest.fixture
def pep_service(
    mock_session: AsyncMock,
    mock_pdf_generator: MagicMock,
    mock_signer: AsyncMock,
    mock_storage: AsyncMock,
    mock_documento_service: AsyncMock,
    mock_atendimento_reader: AsyncMock,
    mock_evolucao_service: AsyncMock,
) -> PEPService:
    return PEPService(
        session=mock_session,
        pdf_generator=mock_pdf_generator,
        signer=mock_signer,
        storage=mock_storage,
        documento_service=mock_documento_service,
        atendimento_reader=mock_atendimento_reader,
        evolucao_service=mock_evolucao_service,
    )


@pytest.mark.asyncio
async def test_pep_service_compilar_pdf(
    pep_service: PEPService,
    mock_documento_service: AsyncMock,
) -> None:
    """compilar_pdf delegates compilation to internal documento_service."""
    doc_id = uuid4()
    mock_documento_service.compilar_pdf.return_value = b"%PDF-test-bytes%"

    pdf_bytes = await pep_service.compilar_pdf(doc_id)

    assert pdf_bytes == b"%PDF-test-bytes%"
    mock_documento_service.compilar_pdf.assert_awaited_once_with(doc_id)


@pytest.mark.asyncio
async def test_pep_service_assinar_documento(
    pep_service: PEPService,
    mock_documento_service: AsyncMock,
) -> None:
    """assinar_documento delegates ICP-Brasil signing to internal documento_service."""
    doc_id = uuid4()
    atend_id = uuid4()
    creds = DoctorCertificateCredentials(token="tok-123", provider="fake")

    expected_result = DocumentoAssinadoResult(
        documento_id=doc_id,
        tipo_documento="RECEITA_SIMPLES",
        sha256_hash="a" * 64,
        assinado_em=datetime.now(UTC),
        tamanho_bytes=1024,
    )
    mock_documento_service.assinar.return_value = expected_result

    result = await pep_service.assinar_documento(
        documento_id=doc_id,
        atendimento_id=atend_id,
        credenciais=creds,
    )

    assert result == expected_result
    mock_documento_service.assinar.assert_awaited_once_with(
        documento_id=doc_id,
        atendimento_id=atend_id,
        credenciais=creds,
    )


@pytest.mark.asyncio
async def test_pep_service_salvar_e_obter_evolucao(
    pep_service: PEPService,
    mock_evolucao_service: AsyncMock,
) -> None:
    """salvar_evolucao_soap and obter_evolucao delegate to evolucao_service."""
    atend_id = uuid4()
    cmd = RegistrarEvolucaoSOAPCommand(
        atendimento_id=atend_id,
        organizacao_id=1,
        medico_id=uuid4(),
        anamnese="Paciente com febre",
        conduta="Prescrito paracetamol",
    )
    mock_evolucao = MagicMock(spec=EvolucaoClinica)
    mock_evolucao_service.salvar_evolucao_soap.return_value = mock_evolucao
    mock_evolucao_service.obter_evolucao.return_value = mock_evolucao

    saved = await pep_service.salvar_evolucao_soap(cmd)
    assert saved == mock_evolucao
    mock_evolucao_service.salvar_evolucao_soap.assert_awaited_once_with(cmd)

    retrieved = await pep_service.obter_evolucao(atend_id)
    assert retrieved == mock_evolucao
    mock_evolucao_service.obter_evolucao.assert_awaited_once_with(atend_id)


@pytest.mark.asyncio
async def test_pep_service_unified_is_terminal(
    pep_service: PEPService,
    mock_atendimento_reader: AsyncMock,
) -> None:
    """_is_terminal checks terminal state via unified reader."""
    atend_id = uuid4()

    # Terminal state
    mock_atendimento_reader.obter_resumo.return_value = AtendimentoResumoDTO(
        atendimento_id=atend_id,
        organizacao_id=1,
        medico_id=uuid4(),
        status="CONCLUIDO",
        tcle_hash="x" * 64,
        is_terminal=True,
    )
    assert await pep_service._is_terminal(atend_id) is True  # pyright: ignore[reportPrivateUsage]

    # Non-terminal state
    mock_atendimento_reader.obter_resumo.return_value = AtendimentoResumoDTO(
        atendimento_id=atend_id,
        organizacao_id=1,
        medico_id=uuid4(),
        status="EM_ATENDIMENTO",
        tcle_hash="x" * 64,
        is_terminal=False,
    )
    assert await pep_service._is_terminal(atend_id) is False  # pyright: ignore[reportPrivateUsage]

    # None state
    mock_atendimento_reader.obter_resumo.return_value = None
    assert await pep_service._is_terminal(atend_id) is False  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_is_atendimento_terminal_helper_handles_none_reader() -> None:
    """is_atendimento_terminal returns False safely if reader is None or raises."""
    assert await is_atendimento_terminal(None, uuid4()) is False

    failing_reader = AsyncMock(spec=AtendimentoReaderPort)
    failing_reader.obter_resumo.side_effect = RuntimeError("database down")
    assert await is_atendimento_terminal(failing_reader, uuid4()) is False


def test_pep_service_defaults_evolucao_service(
    mock_session: AsyncMock,
    mock_pdf_generator: MagicMock,
    mock_signer: AsyncMock,
    mock_storage: AsyncMock,
    mock_documento_service: AsyncMock,
) -> None:
    """PEPService constructs an internal EvolucaoService when none is given."""
    svc = PEPService(
        session=mock_session,
        pdf_generator=mock_pdf_generator,
        signer=mock_signer,
        storage=mock_storage,
        documento_service=mock_documento_service,
        atendimento_reader=None,
        evolucao_service=None,
    )
    assert isinstance(svc.evolucao_service, EvolucaoService)


def test_build_pep_service_for_session(mock_session: AsyncMock) -> None:
    """build_pep_service_for_session constructs a valid PEPService instance."""
    svc = build_pep_service_for_session(session=mock_session)
    assert isinstance(svc, PEPService)
    assert isinstance(svc.documento_service, DocumentoService)
    assert isinstance(svc.evolucao_service, EvolucaoService)
    assert svc.producao_port is not None


@pytest.mark.asyncio
async def test_pep_service_finalizar_consulta_dispara_consolidacao_ambulatorial() -> (
    None
):
    """finalizar_consulta triggers ambulatory BPA-I consolidation when port given."""
    atend_id = uuid4()
    medico_id = uuid4()
    paciente_id = uuid4()

    evolucao = EvolucaoClinica(
        organizacao_id=1,
        atendimento_id=atend_id,
        medico_id=medico_id,
        anamnese="Paciente com tosse",
        conduta="Prescrito xarope",
        codigo_sigtap="03.01.01.025-0",
    )

    fake_session = FakeAsyncSession(results=[FakeResult(evolucao), FakeResult([])])
    resumo = AtendimentoResumoDTO(
        atendimento_id=atend_id,
        organizacao_id=1,
        medico_id=medico_id,
        paciente_id=paciente_id,
        status="EM_ATENDIMENTO",
        tcle_hash="h" * 64,
        is_terminal=False,
    )
    fake_reader = FakeAtendimentoReader(resumo=resumo)
    fake_producao = FakeProducaoAmbulatorialPort()

    svc = PEPService(
        session=fake_session,  # pyright: ignore[reportArgumentType]
        pdf_generator=MagicMock(spec=PDFGeneratorPort),
        signer=AsyncMock(spec=ICPBrasilSignerPort),
        storage=AsyncMock(spec=StoragePort),
        documento_service=AsyncMock(spec=DocumentoService),
        atendimento_reader=fake_reader,
        producao_port=fake_producao,
    )

    cmd = FinalizarConsultaCommand(
        atendimento_id=atend_id,
        organizacao_id=1,
        medico_id=medico_id,
    )

    result = await svc.finalizar_consulta(cmd)

    assert result.atendimento_id == atend_id
    assert result.is_finalizado is True
    assert fake_session.commits == 1

    # Verificação da consolidação ambulatorial BPA-I (ADR-012, US-11)
    assert len(fake_producao.consolidacoes) == 1
    consolidacao = fake_producao.consolidacoes[0]
    assert consolidacao["organizacao_id"] == 1
    assert consolidacao["atendimento_id"] == atend_id
    assert consolidacao["profissional_id"] == medico_id
    assert consolidacao["paciente_id"] == paciente_id
    assert consolidacao["codigo_sigtap"] == "03.01.01.025-0"


@pytest.mark.asyncio
async def test_pep_service_finalizar_consulta_tolera_falha_na_producao() -> None:
    """finalizar_consulta completes even if ambulatory consolidation fails."""
    atend_id = uuid4()
    medico_id = uuid4()
    paciente_id = uuid4()

    evolucao = EvolucaoClinica(
        organizacao_id=1,
        atendimento_id=atend_id,
        medico_id=medico_id,
        anamnese="Paciente com febre",
        conduta="Prescrito antitermico",
        codigo_sigtap="03.01.01.025-0",
    )

    fake_session = FakeAsyncSession(results=[FakeResult(evolucao), FakeResult([])])
    resumo = AtendimentoResumoDTO(
        atendimento_id=atend_id,
        organizacao_id=1,
        medico_id=medico_id,
        paciente_id=paciente_id,
        status="EM_ATENDIMENTO",
        tcle_hash="h" * 64,
        is_terminal=False,
    )
    fake_reader = FakeAtendimentoReader(resumo=resumo)
    failing_producao = AsyncMock(spec=FakeProducaoAmbulatorialPort)
    failing_producao.consolidar_teleconsulta.side_effect = RuntimeError(
        "BPA-I service error"
    )

    svc = PEPService(
        session=fake_session,  # pyright: ignore[reportArgumentType]
        pdf_generator=MagicMock(spec=PDFGeneratorPort),
        signer=AsyncMock(spec=ICPBrasilSignerPort),
        storage=AsyncMock(spec=StoragePort),
        documento_service=AsyncMock(spec=DocumentoService),
        atendimento_reader=fake_reader,
        producao_port=failing_producao,
    )

    cmd = FinalizarConsultaCommand(
        atendimento_id=atend_id,
        organizacao_id=1,
        medico_id=medico_id,
    )

    result = await svc.finalizar_consulta(cmd)
    assert result.is_finalizado is True
    assert fake_session.commits == 1


def _build_test_pep_service(
    session: FakeAsyncSession,
    atendimento_reader: AtendimentoReaderPort | None = None,
    producao_port: FakeProducaoAmbulatorialPort | None = None,
) -> PEPService:
    pdf_gen = FakePDFGenerator()
    signer = FakeICPBrasilSigner()
    storage = FakeMemoryStorage()
    doc_svc = DocumentoService(
        session=session,  # pyright: ignore[reportArgumentType]
        pdf_generator=pdf_gen,
        signer=signer,
        storage=storage,
        cache=MemorySignedCache(),
    )
    return PEPService(
        session=session,  # pyright: ignore[reportArgumentType]
        pdf_generator=pdf_gen,
        signer=signer,
        storage=storage,
        documento_service=doc_svc,
        atendimento_reader=atendimento_reader,
        producao_port=producao_port,
    )


@pytest.mark.asyncio
async def test_pep_warning_on_reader_obter_resumo_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    atend_id = uuid4()
    medico_id = uuid4()

    evolucao = EvolucaoClinica(
        organizacao_id=1,
        atendimento_id=atend_id,
        medico_id=medico_id,
        anamnese="Paciente com dor",
        conduta="Orientação médica",
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
        organizacao_id=1,
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
        organizacao_id=1,
        atendimento_id=atend_id,
        medico_id=medico_id,
        anamnese="Paciente com febre",
        conduta="Prescrição",
    )
    fake_session = FakeAsyncSession(results=[FakeResult(evolucao), FakeResult([])])
    resumo = AtendimentoResumoDTO(
        atendimento_id=atend_id,
        organizacao_id=1,
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
        organizacao_id=1,
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
async def test_pep_warning_on_producao_failure_with_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    atend_id = uuid4()
    medico_id = uuid4()
    paciente_id = uuid4()

    evolucao = EvolucaoClinica(
        organizacao_id=1,
        atendimento_id=atend_id,
        medico_id=medico_id,
        anamnese="Paciente com tosse",
        conduta="Xarope",
        codigo_sigtap="03.01.01.025-0",
    )
    fake_session = FakeAsyncSession(results=[FakeResult(evolucao), FakeResult([])])
    resumo = AtendimentoResumoDTO(
        atendimento_id=atend_id,
        organizacao_id=1,
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
        organizacao_id=1,
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
