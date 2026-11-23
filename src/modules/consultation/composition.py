"""Consultation composition root: concrete adapter wiring (DI Fase 3).

Single place in consultation module allowed to import infrastructure adapters.
Routers and tests must resolve PEPService via get_pep_service/PEPServiceDep
and LiveKit service via get_teleconsulta_service/TeleconsultaServiceDep.
"""

import logging
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import AuditTrailPort, SqlAuditTrailAdapter
from src.core.config import get_settings
from src.core.database import DbSessionDep
from src.core.valkey import ValkeyDep, get_valkey_client, get_valkey_pool
from src.modules.ambulatory.application.dtos import ConsolidarTeleconsultaCommand
from src.modules.ambulatory.application.services.producao_service import (
    ProducaoAmbulatorialService,
)
from src.modules.ambulatory.composition import (
    build_producao_ambulatorial_service,
)
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoHistoricoDTO,
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
from src.modules.consultation.application.ports.liveness_verification_port import (
    LivenessVerificationPort,
)
from src.modules.consultation.application.ports.pdf_generator_port import (
    PDFGeneratorPort,
)
from src.modules.consultation.application.ports.producao_ambulatorial_port import (
    ProducaoAmbulatorialPort,
)
from src.modules.consultation.application.ports.signed_cache_port import (
    SignedCachePort,
)
from src.modules.consultation.application.ports.storage_port import StoragePort
from src.modules.consultation.application.ports.validation_rate_limiter_port import (
    ValidationRateLimiterPort,
)
from src.modules.consultation.application.services.clinical_pdf_compiler import (
    ClinicalPdfCompiler,
)
from src.modules.consultation.application.services.document_validation_service import (
    DocumentValidationService,
)
from src.modules.consultation.application.services.documento_service import (
    DocumentoService,
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
from src.modules.consultation.infrastructure.liveness_adapter import (
    MockLivenessAdapter,
    ValkeyLivenessAdapter,
)
from src.modules.consultation.infrastructure.memory_signed_cache import (
    MemorySignedCache,
)
from src.modules.consultation.infrastructure.pdf_generator import (
    ReportLabPDFGenerator,
)
from src.modules.consultation.infrastructure.pyhanko_signer import (
    CloudPSCOAuth2Client,
    PyHankoSigner,
)
from src.modules.consultation.infrastructure.s3_storage import (
    FakeStorageAdapter,
    S3StorageAdapter,
)
from src.modules.consultation.infrastructure.valkey_signed_cache import (
    ValkeySignedCache,
)
from src.modules.consultation.infrastructure.valkey_validation_rate_limiter import (
    FakeValidationRateLimiter,
    ValkeyValidationRateLimiter,
)
from src.modules.identity.application.ports.identity_reader_port import (
    IdentityReaderPort,
)
from src.modules.identity.composition import get_identity_reader
from src.modules.queue.application.ports.queue_engine_port import QueueEnginePort
from src.modules.queue.application.ports.queue_store_port import QueueStorePort
from src.modules.queue.composition import (
    build_doctor_presence_engine,
    build_fila_service_for_session,
)

logger = logging.getLogger("medisync.consultation.composition")


class QueueStoreAtendimentoReaderAdapter:
    """Adapts QueueStorePort to AtendimentoReaderPort with per-request memoization."""

    def __init__(self, queue_store: QueueStorePort) -> None:
        self._queue_store = queue_store
        self._resumo_cache: dict[UUID, AtendimentoResumoDTO | None] = {}

    async def obter_resumo(self, atendimento_id: UUID) -> AtendimentoResumoDTO | None:
        if atendimento_id in self._resumo_cache:
            return self._resumo_cache[atendimento_id]
        snapshot = await self._queue_store.buscar_atendimento(atendimento_id)
        if snapshot is None:
            self._resumo_cache[atendimento_id] = None
            return None
        resumo = AtendimentoResumoDTO(
            atendimento_id=snapshot.id,
            medico_id=snapshot.medico_id,
            status=snapshot.status,
            tcle_hash=snapshot.tcle_hash,
            is_terminal=snapshot.is_terminal,
            paciente_id=snapshot.paciente_id,
            chamada_iniciada_em=snapshot.chamada_iniciada_em,
            criado_em=snapshot.criado_em,
        )
        self._resumo_cache[atendimento_id] = resumo
        return resumo

    async def concluir_atendimento(
        self,
        atendimento_id: UUID,
        *,
        auto_commit: bool = True,
    ) -> UUID | None:
        self._resumo_cache.pop(atendimento_id, None)
        return await self._queue_store.concluir_atendimento(
            atendimento_id,
            auto_commit=auto_commit,
        )

    async def liberar_consulta_ativa_medico(self, medico_id: UUID) -> None:
        await self._queue_store.liberar_consulta_ativa_medico(medico_id)

    async def atender_chamada(self, atendimento_id: UUID) -> None:
        self._resumo_cache.pop(atendimento_id, None)
        await self._queue_store.atender_chamada(atendimento_id)

    async def listar_historico_paciente(
        self,
        paciente_id: UUID,
    ) -> list[AtendimentoHistoricoDTO]:
        items = await self._queue_store.listar_historico_paciente(paciente_id)
        return [
            AtendimentoHistoricoDTO(
                atendimento_id=item.atendimento_id,
                paciente_id=item.paciente_id,
                status=item.status,
                prioridade_clinica=item.prioridade_clinica,
                criado_em=item.criado_em,
                finalizado_em=item.finalizado_em,
                medico_id=item.medico_id,
                queixa_principal=item.queixa_principal,
            )
            for item in items
        ]


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
        medico_id: UUID,
        atendimento_id: UUID,
    ) -> DadosVerificacaoDirectory:
        """Obtém dados de verificação pública do documento via portas de domínio.

        Regras: docs/adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md e
        docs/adrs/ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md.
        """
        snapshot = await self._queue_store.buscar_atendimento(atendimento_id)
        if snapshot is None:
            raise DocumentoIntegridadeError(
                f"Atendimento '{atendimento_id}' ausente para verificação do documento "
                "(esperado atendimento registrado)."
            )

        try:
            dto = await self._identity_reader.obter_dados_diretorio(
                medico_id=medico_id,
                paciente_id=snapshot.paciente_id,
            )
        except Exception as exc:
            raise DocumentoIntegridadeError(
                f"Dados de diretório ausentes ou incompletos para médico '{medico_id}' "
                f"e atendimento '{atendimento_id}'."
            ) from exc

        nasc_str = (
            dto.paciente_data_nascimento.strftime("%d/%m/%Y")
            if dto.paciente_data_nascimento
            else None
        )
        ausentes = [
            campo
            for campo, valor in (
                ("organizacao_nome", dto.organizacao_nome),
                ("medico_nome", dto.medico_nome),
                ("medico_crm", dto.medico_crm),
                ("medico_crm_uf", dto.medico_crm_uf),
                ("paciente_nome", dto.paciente_nome),
                ("paciente_cpf", dto.paciente_cpf),
            )
            if not valor or not str(valor).strip()
        ]
        if (
            ausentes
            or dto.medico_crm is None
            or dto.medico_crm_uf is None
            or dto.paciente_cpf is None
        ):
            raise DocumentoIntegridadeError(
                f"Dados obrigatórios de diretório ausentes para médico '{medico_id}' e "
                f"atendimento '{atendimento_id}': campos {ausentes}."
            )

        return DadosVerificacaoDirectory(
            organizacao_nome=dto.organizacao_nome.strip(),
            medico_nome=dto.medico_nome.strip(),
            medico_crm=dto.medico_crm.strip(),
            medico_crm_uf=dto.medico_crm_uf.strip(),
            paciente_nome=dto.paciente_nome.strip(),
            paciente_cpf=dto.paciente_cpf.strip(),
            organizacao_cnpj=dto.organizacao_cnpj,
            paciente_data_nascimento=nasc_str,
            paciente_endereco=dto.paciente_endereco,
            cnes=dto.cnes,
        )


class AmbulatoryProducaoAdapter(ProducaoAmbulatorialPort):
    """Adapts ProducaoAmbulatorialService for consultation (ADR-012)."""

    def __init__(
        self,
        producao_service: ProducaoAmbulatorialService,
        directory: DocumentDirectoryPort | None = None,
    ) -> None:
        self._producao_service = producao_service
        self._directory = directory

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
        cnes_final = cnes
        if not cnes_final and self._directory is not None:
            try:
                dados = await self._directory.obter_dados_verificacao(
                    medico_id=profissional_id,
                    atendimento_id=atendimento_id,
                )
                cnes_final = dados.cnes
            except Exception as exc:
                logger.warning(
                    "Falha ao obter CNES do diretório para atendimento '%s': %s",
                    atendimento_id,
                    exc,
                )

        cnes_final = cnes_final or "0000000"

        cmd = ConsolidarTeleconsultaCommand(
            atendimento_id=atendimento_id,
            profissional_id=profissional_id,
            paciente_id=paciente_id,
            cnes=cnes_final,
            codigo_sigtap=codigo_sigtap,
            carater_atendimento=carater_atendimento,
        )
        await self._producao_service.consolidar_teleconsulta(cmd, auto_commit=False)


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
    """Provide ICP-Brasil PAdES signer adapter with injected PSC endpoints."""
    settings = get_settings()
    allow_fake = settings.ENVIRONMENT != "production" or settings.DEBUG
    psc_client = CloudPSCOAuth2Client(
        provider_endpoints={
            "birdid": settings.PSC_BIRDID_ENDPOINT,
            "safeid": settings.PSC_SAFEID_ENDPOINT,
            "vidaas": settings.PSC_VIDAAS_ENDPOINT,
        }
    )
    return PyHankoSigner(psc_client=psc_client, allow_fake=allow_fake)


@lru_cache(maxsize=1)
def get_signed_cache() -> SignedCachePort:
    """Provide process-wide signed-document cache based on active settings."""
    settings = get_settings()
    if settings.SIGNED_CACHE_BACKEND == "memory":
        return MemorySignedCache()
    return ValkeySignedCache()


def build_atendimento_reader_for_session(
    session: AsyncSession,
    valkey: Redis | None = None,
) -> AtendimentoReaderPort:
    """Build attendance reader adapting QueueStorePort with optional Valkey client."""
    try:
        queue_store: QueueStorePort = build_fila_service_for_session(
            session=session,
            valkey=valkey,
        )
        return QueueStoreAtendimentoReaderAdapter(queue_store)
    except Exception as exc:
        logger.warning(
            "Falha ao instanciar QueueStoreAtendimentoReaderAdapter, "
            "usando fallback SqlAtendimentoReader: %s",
            exc,
        )
        return SqlAtendimentoReader(session)


def get_atendimento_reader(
    session: DbSessionDep,
    valkey: Annotated[Redis | None, Depends(get_valkey_client)] = None,
) -> AtendimentoReaderPort:
    """Provide attendance reader adapting QueueStorePort with ORM models."""
    return build_atendimento_reader_for_session(session=session, valkey=valkey)


def get_doctor_presence_registrar(valkey: ValkeyDep) -> QueueEnginePort:
    """Provide QueueEnginePort for registering connected doctors on WS connect."""
    return build_doctor_presence_engine(valkey=valkey)


DoctorPresenceDep = Annotated[QueueEnginePort, Depends(get_doctor_presence_registrar)]


def get_document_directory(session: DbSessionDep) -> DocumentDirectoryPort:
    """Provide directory adapter using identity and queue ORM ports."""
    try:
        identity_reader: IdentityReaderPort = get_identity_reader(session)
        queue_store: QueueStorePort = build_fila_service_for_session(session=session)
        return IdentityDocumentDirectoryAdapter(identity_reader, queue_store)
    except Exception as exc:
        logger.warning(
            "Falha ao instanciar IdentityDocumentDirectoryAdapter, "
            "usando fallback SqlDocumentDirectory: %s",
            exc,
        )
        return SqlDocumentDirectory(session)


def get_liveness_verifier(valkey: Redis | None = None) -> LivenessVerificationPort:
    """Resolve adaptador ativo para prova de vida facial (US-15)."""
    settings = get_settings()
    if settings.LIVENESS_PROVIDER == "mock":
        if settings.ENVIRONMENT == "production":
            raise RuntimeError(
                "Provedor 'mock' de prova de vida é proibido em produção."
            )
        return MockLivenessAdapter()
    if settings.LIVENESS_PROVIDER == "valkey_sandbox":
        if settings.ENVIRONMENT == "production":
            raise RuntimeError(
                "Provedor 'valkey_sandbox' de prova de vida é proibido em produção."
            )
        client = (
            valkey if valkey is not None else Redis(connection_pool=get_valkey_pool())
        )
        return ValkeyLivenessAdapter(valkey=client)
    raise NotImplementedError(
        f"Provedor biométrico '{settings.LIVENESS_PROVIDER}' ainda não possui "
        "credenciais/SDK configurados neste ambiente; esperado gov.br/Datavalid."
    )


def build_pdf_compiler_for_session(
    session: AsyncSession,
    pdf_generator: PDFGeneratorPort | None = None,
    storage: StoragePort | None = None,
    document_directory: DocumentDirectoryPort | None = None,
) -> ClinicalPdfCompiler:
    """Build ClinicalPdfCompiler without Signer/Liveness overhead (ADR-001/006)."""
    return ClinicalPdfCompiler(
        session=session,
        pdf_generator=pdf_generator
        if pdf_generator is not None
        else get_pdf_generator(),
        storage=storage if storage is not None else get_storage(),
        directory=(
            document_directory
            if document_directory is not None
            else get_document_directory(session)
        ),
    )


def get_documento_service(
    session: DbSessionDep,
    reader: Annotated[
        AtendimentoReaderPort | None, Depends(get_atendimento_reader)
    ] = None,
    valkey: Annotated[Redis | None, Depends(get_valkey_client)] = None,
) -> DocumentoService:
    """Build DocumentoService owning emitir/compilar/assinar canonical keys."""
    resolved_reader = (
        reader
        if reader is not None
        else build_atendimento_reader_for_session(session=session, valkey=valkey)
    )
    directory = get_document_directory(session)
    pdf_gen = get_pdf_generator()
    stor = get_storage()
    compiler = build_pdf_compiler_for_session(
        session=session,
        pdf_generator=pdf_gen,
        storage=stor,
        document_directory=directory,
    )
    return DocumentoService(
        session=session,
        pdf_generator=pdf_gen,
        signer=get_signer(),
        storage=stor,
        cache=get_signed_cache(),
        atendimento_reader=resolved_reader,
        directory=directory,
        audit_trail=SqlAuditTrailAdapter(session),
        liveness_verifier=get_liveness_verifier(valkey),
        pdf_compiler=compiler,
    )


DocumentoServiceDep = Annotated[DocumentoService, Depends(get_documento_service)]


def build_pep_service_for_session(
    session: AsyncSession,
    atendimento_reader: AtendimentoReaderPort | None = None,
    document_directory: DocumentDirectoryPort | None = None,
    pdf_generator: PDFGeneratorPort | None = None,
    storage: StoragePort | None = None,
    pdf_compiler: ClinicalPdfCompiler | None = None,
    audit_trail: AuditTrailPort | None = None,
    producao_port: ProducaoAmbulatorialPort | None = None,
    valkey: Redis | None = None,
) -> PEPService:
    """Build deep PEPService without Signer/Liveness dependencies."""
    reader = (
        atendimento_reader
        if atendimento_reader is not None
        else build_atendimento_reader_for_session(session, valkey=valkey)
    )
    directory = (
        document_directory
        if document_directory is not None
        else get_document_directory(session)
    )
    compiler = (
        pdf_compiler
        if pdf_compiler is not None
        else build_pdf_compiler_for_session(
            session=session,
            pdf_generator=pdf_generator,
            storage=storage,
            document_directory=directory,
        )
    )
    audit = audit_trail if audit_trail is not None else SqlAuditTrailAdapter(session)

    prod_port = (
        producao_port
        if producao_port is not None
        else AmbulatoryProducaoAdapter(
            producao_service=build_producao_ambulatorial_service(
                session=session,
                audit_trail=audit,
            ),
            directory=directory,
        )
    )

    return PEPService(
        session=session,
        pdf_compiler=compiler,
        atendimento_reader=reader,
        audit_trail=audit,
        producao_port=prod_port,
    )


def get_pep_service(
    session: DbSessionDep,
    reader: Annotated[
        AtendimentoReaderPort | None, Depends(get_atendimento_reader)
    ] = None,
    valkey: Annotated[Redis | None, Depends(get_valkey_client)] = None,
) -> PEPService:
    """Build PEPService sharing request-scoped AtendimentoReaderPort."""
    return build_pep_service_for_session(
        session,
        atendimento_reader=reader,
        valkey=valkey,
    )


PEPServiceDep = Annotated[PEPService, Depends(get_pep_service)]


def get_validation_rate_limiter() -> ValidationRateLimiterPort:
    """Provide validation rate limiter adapter based on active settings."""
    settings = get_settings()
    if settings.VALIDATION_RATE_LIMIT_BACKEND == "memory":
        return FakeValidationRateLimiter()
    return ValkeyValidationRateLimiter()


ValidationRateLimiterDep = Annotated[
    ValidationRateLimiterPort, Depends(get_validation_rate_limiter)
]


def get_document_validation_service(
    session: DbSessionDep,
) -> DocumentValidationService:
    """Build DocumentValidationService directly on ClinicalPdfCompiler seam."""
    directory = get_document_directory(session)
    stor = get_storage()
    compiler = build_pdf_compiler_for_session(
        session=session,
        storage=stor,
        document_directory=directory,
    )
    return DocumentValidationService(
        session=session,
        directory=directory,
        storage=stor,
        compilador_pdf=compiler.compilar,
        cache=get_signed_cache(),
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


def build_teleconsulta_service_for_session(
    session: AsyncSession,
    media_port: LiveKitMediaPort | None = None,
    atendimento_reader: AtendimentoReaderPort | None = None,
) -> TeleconsultaService:
    """Build TeleconsultaService outside request scope (tests/worker tooling)."""
    adapter = media_port if media_port is not None else get_livekit_adapter()
    reader = (
        atendimento_reader
        if atendimento_reader is not None
        else get_atendimento_reader(session)
    )
    server_url = getattr(adapter, "server_url", "http://localhost:7880")
    return TeleconsultaService(
        media_port=adapter,
        server_url=server_url,
        atendimento_reader=reader,
    )


def get_teleconsulta_service(
    session: DbSessionDep,
    adapter: Annotated[LiveKitMediaPort, Depends(get_livekit_adapter)],
    reader: Annotated[AtendimentoReaderPort, Depends(get_atendimento_reader)],
) -> TeleconsultaService:
    """Build TeleconsultaService with media port adapter and attendance reader."""
    return build_teleconsulta_service_for_session(
        session=session,
        media_port=adapter,
        atendimento_reader=reader,
    )


TeleconsultaServiceDep = Annotated[
    TeleconsultaService, Depends(get_teleconsulta_service)
]
