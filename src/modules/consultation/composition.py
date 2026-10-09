"""Consultation composition root: concrete adapter wiring (DI Fase 3).

Single place in consultation module allowed to import infrastructure adapters.
Routers and tests must resolve PEPService via get_pep_service/PEPServiceDep
and LiveKit service via get_teleconsulta_service/TeleconsultaServiceDep.
"""

from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends

from src.core.config import get_settings
from src.core.database import DbSessionDep
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoReaderPort,
    AtendimentoResumoDTO,
)
from src.modules.consultation.application.ports.document_directory_port import (
    DadosVerificacaoDirectory,
    DocumentDirectoryPort,
)
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    ICPBrasilSignerPort,
)
from src.modules.consultation.application.ports.livekit_media_port import (
    LiveKitMediaPort,
)
from src.modules.consultation.application.ports.pdf_generator_port import (
    PDFGeneratorPort,
)
from src.modules.consultation.application.ports.signed_cache_port import (
    SignedCachePort,
)
from src.modules.consultation.application.ports.storage_port import StoragePort
from src.modules.consultation.application.ports.validation_rate_limiter_port import (
    ValidationRateLimiterPort,
)
from src.modules.consultation.application.services.document_validation_service import (
    DocumentValidationService,
)
from src.modules.consultation.application.services.documento_service import (
    DocumentoService,
)
from src.modules.consultation.application.services.evolucao_service import (
    EvolucaoService,
)
from src.modules.consultation.application.services.pep_service import PEPService
from src.modules.consultation.application.services.teleconsulta_service import (
    TeleconsultaService,
)
from src.modules.consultation.domain.exceptions import DocumentoIntegridadeError
from src.modules.consultation.infrastructure.atendimento_reader_sql import (
    SqlAtendimentoReader,
)
from src.modules.consultation.infrastructure.document_directory_sql import (
    SqlDocumentDirectory,
)
from src.modules.consultation.infrastructure.livekit_adapter import LiveKitAdapter
from src.modules.consultation.infrastructure.memory_signed_cache import (
    MemorySignedCache,
)
from src.modules.consultation.infrastructure.pdf_generator import (
    ReportLabPDFGenerator,
)
from src.modules.consultation.infrastructure.pyhanko_signer import PyHankoSigner
from src.modules.consultation.infrastructure.s3_storage import (
    FakeStorageAdapter,
    S3StorageAdapter,
)
from src.modules.consultation.infrastructure.valkey_validation_rate_limiter import (
    ValkeyValidationRateLimiter,
)
from src.modules.identity.application.ports.identity_reader_port import (
    IdentityReaderPort,
)
from src.modules.identity.composition import get_identity_reader
from src.modules.queue.application.ports.queue_store_port import QueueStorePort
from src.modules.queue.composition import build_fila_service_for_session


class QueueStoreAtendimentoReaderAdapter:
    """Adapts QueueStorePort to consultation's AtendimentoReaderPort without raw SQL."""

    def __init__(self, queue_store: QueueStorePort) -> None:
        self._queue_store = queue_store

    async def obter_resumo(self, atendimento_id: UUID) -> AtendimentoResumoDTO | None:
        snapshot = await self._queue_store.buscar_atendimento(atendimento_id)
        if snapshot is None:
            return None
        return AtendimentoResumoDTO(
            atendimento_id=snapshot.id,
            organizacao_id=snapshot.organizacao_id,
            medico_id=snapshot.medico_id,
            status=snapshot.status,
            tcle_hash=snapshot.tcle_hash,
            is_terminal=snapshot.is_terminal,
            paciente_id=snapshot.paciente_id,
        )

    async def concluir_atendimento(self, atendimento_id: UUID) -> None:
        await self._queue_store.concluir_atendimento(atendimento_id)


class IdentityDocumentDirectoryAdapter:
    """Adapts IdentityReaderPort and QueueStorePort to DocumentDirectoryPort.

    Uses chainable ORM queries without raw SQL.
    """

    def __init__(
        self,
        identity_reader: IdentityReaderPort,
        queue_store: QueueStorePort,
    ) -> None:
        self._identity_reader = identity_reader
        self._queue_store = queue_store

    async def obter_dados_verificacao(
        self,
        organizacao_id: int,
        medico_id: UUID,
        atendimento_id: UUID,
    ) -> DadosVerificacaoDirectory:
        snapshot = await self._queue_store.buscar_atendimento(atendimento_id)
        if snapshot is None:
            raise DocumentoIntegridadeError("Atendimento ausente para o documento.")

        try:
            dto = await self._identity_reader.obter_dados_diretorio(
                organizacao_id=organizacao_id,
                medico_id=medico_id,
                paciente_id=snapshot.paciente_id,
            )
        except Exception as exc:
            raise DocumentoIntegridadeError(
                "Dados de diretório ausentes ou incompletos."
            ) from exc

        nasc_str = (
            dto.paciente_data_nascimento.strftime("%d/%m/%Y")
            if dto.paciente_data_nascimento
            else None
        )

        return DadosVerificacaoDirectory(
            organizacao_nome=dto.organizacao_nome,
            medico_nome=dto.medico_nome,
            medico_crm=dto.medico_crm or "00000",
            medico_crm_uf=dto.medico_crm_uf or "BR",
            paciente_nome=dto.paciente_nome,
            paciente_cpf=dto.paciente_cpf or "000.000.000-00",
            organizacao_cnpj=dto.organizacao_cnpj,
            paciente_data_nascimento=nasc_str,
            paciente_endereco=dto.paciente_endereco,
        )


@lru_cache(maxsize=1)
def get_storage() -> StoragePort:
    """Provide process-wide object storage adapter (single Fake/S3 instance)."""
    settings = get_settings()
    if settings.STORAGE_BACKEND == "s3":
        return S3StorageAdapter(
            endpoint_url=settings.S3_ENDPOINT_URL,
            bucket_name=settings.S3_BUCKET_NAME,
            access_key=settings.S3_ACCESS_KEY_ID,
            secret_key=settings.S3_SECRET_ACCESS_KEY,
            region_name=settings.S3_REGION_NAME,
        )
    return FakeStorageAdapter(bucket_name=settings.S3_BUCKET_NAME)


def get_pdf_generator() -> PDFGeneratorPort:
    """Provide ReportLab PDF/A generator adapter."""
    settings = get_settings()
    return ReportLabPDFGenerator(
        validation_url_prefix=settings.DOCUMENTS_VALIDATION_URL_PREFIX
    )


def get_signer() -> ICPBrasilSignerPort:
    """Provide ICP-Brasil PAdES signer adapter."""
    return PyHankoSigner()


@lru_cache(maxsize=1)
def get_signed_cache() -> SignedCachePort:
    """Provide process-wide signed-document cache (single Memory instance)."""
    return MemorySignedCache()


def get_atendimento_reader(session: DbSessionDep) -> AtendimentoReaderPort:
    """Provide attendance reader adapting QueueStorePort with ORM models."""
    try:
        queue_store: QueueStorePort = build_fila_service_for_session(session=session)
        return QueueStoreAtendimentoReaderAdapter(queue_store)
    except Exception:
        return SqlAtendimentoReader(session)


def get_document_directory(session: DbSessionDep) -> DocumentDirectoryPort:
    """Provide directory adapter using identity and queue ORM ports."""
    try:
        identity_reader: IdentityReaderPort = get_identity_reader(session)
        queue_store: QueueStorePort = build_fila_service_for_session(session=session)
        return IdentityDocumentDirectoryAdapter(identity_reader, queue_store)
    except Exception:
        return SqlDocumentDirectory(session)


def get_documento_service(session: DbSessionDep) -> DocumentoService:
    """Build DocumentoService owning emitir/compilar/assinar canonical keys."""
    return DocumentoService(
        session=session,
        pdf_generator=get_pdf_generator(),
        signer=get_signer(),
        storage=get_storage(),
        cache=get_signed_cache(),
        atendimento_reader=get_atendimento_reader(session),
        directory=get_document_directory(session),
    )


def get_evolucao_service(
    session: DbSessionDep,
    reader: AtendimentoReaderPort | None = None,
) -> EvolucaoService:
    """Build EvolucaoService owning SOAP persistence with terminal guard."""
    return EvolucaoService(
        session=session,
        reader=reader if reader is not None else get_atendimento_reader(session),
    )


DocumentoServiceDep = Annotated[DocumentoService, Depends(get_documento_service)]


def get_pep_service(session: DbSessionDep) -> PEPService:
    """Build PEPService with all mandatory ports wired (no infra defaults)."""
    reader = get_atendimento_reader(session)
    documento_service = get_documento_service(session)
    evolucao_service = get_evolucao_service(session, reader)
    return PEPService(
        session=session,
        pdf_generator=get_pdf_generator(),
        signer=get_signer(),
        storage=documento_service.storage,
        documento_service=documento_service,
        atendimento_reader=reader,
        evolucao_service=evolucao_service,
    )


PEPServiceDep = Annotated[PEPService, Depends(get_pep_service)]


def get_validation_rate_limiter() -> ValidationRateLimiterPort:
    """Provide Valkey sliding-window limiter for public validation endpoints."""
    return ValkeyValidationRateLimiter()


ValidationRateLimiterDep = Annotated[
    ValidationRateLimiterPort, Depends(get_validation_rate_limiter)
]


def get_document_validation_service(
    session: DbSessionDep,
    directory: Annotated[DocumentDirectoryPort, Depends(get_document_directory)],
) -> DocumentValidationService:
    """Build DocumentValidationService with directory, storage and PDF compiler."""
    documento_service = get_documento_service(session)
    return DocumentValidationService(
        session=session,
        directory=directory,
        storage=documento_service.storage,
        compilador_pdf=documento_service.compilar_pdf,
        cache=documento_service.cache,
    )


DocumentValidationServiceDep = Annotated[
    DocumentValidationService, Depends(get_document_validation_service)
]


def get_livekit_adapter() -> LiveKitMediaPort:
    """Provide configured LiveKit SFU adapter instance."""
    settings = get_settings()
    return LiveKitAdapter(
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
        server_url=settings.LIVEKIT_URL,
    )


LiveKitAdapterDep = Annotated[LiveKitMediaPort, Depends(get_livekit_adapter)]


def get_teleconsulta_service(
    adapter: Annotated[LiveKitMediaPort, Depends(get_livekit_adapter)],
) -> TeleconsultaService:
    """Build TeleconsultaService with media port adapter."""
    server_url = getattr(adapter, "server_url", "http://localhost:7880")
    return TeleconsultaService(
        media_port=adapter,
        server_url=server_url,
    )


TeleconsultaServiceDep = Annotated[
    TeleconsultaService, Depends(get_teleconsulta_service)
]
