"""Consultation composition root: concrete adapter wiring (DI Fase 3).

Single place in consultation module allowed to import infrastructure adapters.
Routers and tests must resolve PEPService via get_pep_service/PEPServiceDep
and LiveKit adapter via get_livekit_adapter/LiveKitAdapterDep.
"""

from typing import Annotated

from fastapi import Depends

from src.core.config import get_settings
from src.core.database import DbSessionDep
from src.modules.consultation.application.ports.document_directory_port import (
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
from src.modules.consultation.application.services.pep_service import PEPService
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


def get_storage() -> StoragePort:
    """Provide object storage adapter selected by STORAGE_BACKEND setting."""
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


def get_signed_cache() -> SignedCachePort:
    """Provide process-local signed-document cache (tests/single-worker)."""
    return MemorySignedCache()


# Multi-worker production wiring (requires a shared Valkey client):
# def get_signed_cache_valkey(valkey: Redis) -> SignedCachePort:
#     from src.modules.consultation.infrastructure.valkey_signed_cache import (
#         ValkeySignedCache,
#     )
#     return ValkeySignedCache(valkey)


def get_documento_service(session: DbSessionDep) -> DocumentoService:
    """Build DocumentoService owning emitir/compilar/assinar canonical keys."""
    return DocumentoService(
        session=session,
        pdf_generator=get_pdf_generator(),
        signer=get_signer(),
        storage=get_storage(),
        cache=get_signed_cache(),
    )


def get_pep_service(session: DbSessionDep) -> PEPService:
    """Build PEPService with all mandatory ports wired (no infra defaults)."""
    documento_service = get_documento_service(session)
    return PEPService(
        session=session,
        pdf_generator=get_pdf_generator(),
        signer=get_signer(),
        storage=documento_service.storage,
        documento_service=documento_service,
    )


PEPServiceDep = Annotated[PEPService, Depends(get_pep_service)]


def get_document_directory(session: DbSessionDep) -> DocumentDirectoryPort:
    """Provide SQL directory adapter isolated in infra (no identity imports)."""
    return SqlDocumentDirectory(session)


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
