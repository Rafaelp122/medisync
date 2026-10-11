"""Unit tests for PEPService: single facade, compilar_pdf, assinar_documento."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.modules.consultation.application.dtos import (
    DocumentoAssinadoResult,
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
