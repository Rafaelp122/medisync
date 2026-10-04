"""Consultation composition root: concrete adapter wiring (DI Fase 3).

Single place in consultation module allowed to import infrastructure adapters.
Routers and tests must resolve PEPService via get_pep_service/PEPServiceDep
and LiveKit adapter via get_livekit_adapter/LiveKitAdapterDep.
"""

from typing import Annotated

from fastapi import Depends

from src.core.config import get_settings
from src.core.database import DbSessionDep
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    ICPBrasilSignerPort,
)
from src.modules.consultation.application.ports.livekit_media_port import (
    LiveKitMediaPort,
)
from src.modules.consultation.application.ports.pdf_generator_port import (
    PDFGeneratorPort,
)
from src.modules.consultation.application.ports.storage_port import StoragePort
from src.modules.consultation.application.services.pep_service import PEPService
from src.modules.consultation.infrastructure.livekit_adapter import LiveKitAdapter
from src.modules.consultation.infrastructure.pdf_generator import (
    ReportLabPDFGenerator,
)
from src.modules.consultation.infrastructure.pyhanko_signer import PyHankoSigner
from src.modules.consultation.infrastructure.s3_storage import (
    FakeStorageAdapter,
    S3StorageAdapter,
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


def get_pep_service(session: DbSessionDep) -> PEPService:
    """Build PEPService with all mandatory ports wired (no infra defaults)."""
    return PEPService(
        session=session,
        pdf_generator=get_pdf_generator(),
        signer=get_signer(),
        storage=get_storage(),
    )


PEPServiceDep = Annotated[PEPService, Depends(get_pep_service)]


def get_livekit_adapter() -> LiveKitMediaPort:
    """Provide configured LiveKit SFU adapter instance."""
    settings = get_settings()
    return LiveKitAdapter(
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
        server_url=settings.LIVEKIT_URL,
    )


LiveKitAdapterDep = Annotated[LiveKitMediaPort, Depends(get_livekit_adapter)]
