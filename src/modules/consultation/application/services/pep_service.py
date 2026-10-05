"""PEP clinical workflow service enforcing SOAP and Portaria 344/98 safeguards."""

import contextlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.modules.consultation.application.dtos import (
    EmitirDocumentoClinicoCommand,
    FinalizarConsultaCommand,
    ProntuarioResumoDTO,
    RegistrarEvolucaoSOAPCommand,
    TMAStatusDTO,
)
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoReaderPort,
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
from src.modules.consultation.domain.exceptions import (
    ConsultaFinalizadaError,
    ConsultaInvalidaError,
)
from src.modules.consultation.domain.models import (
    DocumentoClinico,
    EvolucaoClinica,
)
from src.modules.consultation.domain.models._substances import (
    validar_substancia_permitida_telemedicina,
)
from src.modules.consultation.domain.s3_keys import is_signed_document_key


class PEPService:
    """Application service for Electronic Health Record (PEP) and SOAP workflow."""

    def __init__(
        self,
        session: AsyncSession,
        pdf_generator: PDFGeneratorPort,
        signer: ICPBrasilSignerPort,
        storage: StoragePort,
        documento_service: DocumentoService | None = None,
        atendimento_reader: AtendimentoReaderPort | None = None,
        evolucao_service: EvolucaoService | None = None,
    ) -> None:
        self._session = session
        self._pdf_generator = pdf_generator
        self._signer = signer
        self._storage = storage
        self._reader = atendimento_reader
        self._documentos = (
            documento_service
            if documento_service is not None
            else DocumentoService(
                session=session,
                pdf_generator=pdf_generator,
                signer=signer,
                storage=storage,
            )
        )
        self._evolucao = (
            evolucao_service
            if evolucao_service is not None
            else EvolucaoService(session=session, reader=atendimento_reader)
        )

    @property
    def storage(self) -> StoragePort:
        """Return the injected storage port instance."""
        return self._storage

    @property
    def documento_service(self) -> DocumentoService:
        """Return the owned clinical document lifecycle service."""
        return self._documentos

    @property
    def evolucao_service(self) -> EvolucaoService:
        """Return the owned SOAP evolution service."""
        return self._evolucao

    @property
    def atendimento_reader(self) -> AtendimentoReaderPort | None:
        """Return the injected attendance reader port, if any."""
        return self._reader

    async def _is_terminal(self, atendimento_id: UUID) -> bool:
        """Return True when queue-owned attendance reached terminal status."""
        if self._reader is None:
            return False
        try:
            resumo = await self._reader.obter_resumo(atendimento_id)
        except Exception:
            return False
        return bool(resumo is not None and resumo.is_terminal)

    def is_documento_assinado(self, doc: DocumentoClinico) -> bool:
        """Deprecated: prefer DocumentoService.is_assinado (async, cache-aware)."""
        return is_signed_document_key(doc.chave_s3, doc.organizacao_id)

    async def salvar_evolucao_soap(
        self, command: RegistrarEvolucaoSOAPCommand
    ) -> EvolucaoClinica:
        """Delegate SOAP evolution persistence to EvolucaoService."""
        return await self._evolucao.salvar_evolucao_soap(command)

    def validar_prescricao(self, medicamento: str) -> None:
        """Validate single medication against Portaria 344/98 Lists A & B."""
        validar_substancia_permitida_telemedicina(medicamento)

    async def emitir_documento(
        self, command: EmitirDocumentoClinicoCommand
    ) -> DocumentoClinico:
        """Delegate clinical document issuance to DocumentoService."""
        return await self._documentos.emitir_documento(command)

    async def finalizar_consulta(
        self, command: FinalizarConsultaCommand
    ) -> EvolucaoClinica:
        """Lock PEP evolution and documents, enforcing clinical record immutability."""
        stmt = select(EvolucaoClinica).where(
            EvolucaoClinica.atendimento_id == command.atendimento_id
        )
        res = await self._session.execute(stmt)
        evolucao = res.scalar_one_or_none()

        if evolucao is None:
            raise ConsultaInvalidaError(
                "Atendimento sem evolução clínica preenchida. É obrigatório registrar "
                "a evolução SOAP antes da finalização."
            )

        is_term = await self._is_terminal(command.atendimento_id)
        if evolucao.is_finalizado or is_term:
            evolucao.marcar_finalizado()
            raise ConsultaFinalizadaError(
                "A consulta já se encontra finalizada e imutável."
            )

        evolucao.marcar_finalizado()

        # Mark all documents as finalized
        doc_stmt = select(DocumentoClinico).where(
            DocumentoClinico.atendimento_id == command.atendimento_id
        )
        doc_res = await self._session.execute(doc_stmt)
        documentos = doc_res.scalars().all()
        for doc in documentos:
            doc.marcar_finalizado()

        # NOTE (Task 7 follow-up): atendimentos.status is queue-owned (ADR-001)
        # and this UPDATE should move behind a queue status-transition port.
        # Kept because EvolucaoClinica.is_finalizado is in-memory only (no DB
        # column): CONCLUIDO is today the sole persistent finalization marker
        # enforcing cross-session immutability. Removing it breaks
        # test_finalizar_consulta_service_commit_visivel_outra_sessao and the
        # post-finalize 409 guards. Do not delete without a persistent marker.
        with contextlib.suppress(Exception):
            update_stmt = text(
                "UPDATE atendimentos SET status = 'CONCLUIDO', "
                "chamada_finalizada_em = :now, atualizado_em = :now "
                "WHERE id = :atend_id"
            )
            await self._session.execute(
                update_stmt,
                {"atend_id": command.atendimento_id, "now": datetime.now(UTC)},
            )

        await self._session.flush()
        await self._session.commit()
        return evolucao

    def calcular_tma_status(
        self,
        atendimento_id: UUID,
        iniciado_em: datetime | None = None,
        tma_planejado_segundos: int = 900,
    ) -> TMAStatusDTO:
        """Compute TMA indicators while preserving sovereign medical act (RN06).

        Under RN06, exceeding TMA generates only discrete visual telemetry.
        Software is strictly forbidden from forcing disconnection.
        """
        now = datetime.now(UTC)
        inicio_raw = iniciado_em or now
        iniciado_utc = (
            inicio_raw
            if inicio_raw.tzinfo is not None
            else inicio_raw.replace(tzinfo=UTC)
        )
        decorrido = max(0, int((now - iniciado_utc).total_seconds()))
        excedeu = decorrido > tma_planejado_segundos

        if excedeu:
            diferenca = decorrido - tma_planejado_segundos
            aviso = (
                f"TMA ultrapassado em {diferenca}s. Teleconsulta em curso "
                "preservada sem desconexão forçada (RN06)."
            )
        else:
            aviso = f"Dentro do TMA previsto ({decorrido}/{tma_planejado_segundos}s)."

        return TMAStatusDTO(
            atendimento_id=atendimento_id,
            tempo_decorrido_segundos=decorrido,
            tma_planejado_segundos=tma_planejado_segundos,
            excedeu_tma=excedeu,
            aviso_visual=aviso,
        )

    async def obter_prontuario(self, atendimento_id: UUID) -> ProntuarioResumoDTO:
        """Retrieve aggregated clinical record view for an attendance."""
        stmt = select(EvolucaoClinica).where(
            EvolucaoClinica.atendimento_id == atendimento_id
        )
        res = await self._session.execute(stmt)
        evolucao = res.scalar_one_or_none()

        doc_stmt = (
            select(DocumentoClinico)
            .where(DocumentoClinico.atendimento_id == atendimento_id)
            .options(selectinload(DocumentoClinico.itens))
        )
        doc_res = await self._session.execute(doc_stmt)
        documentos = list(doc_res.scalars().all())

        is_term = await self._is_terminal(atendimento_id)
        is_finalizado = bool((evolucao and evolucao.is_finalizado) or is_term)
        if evolucao and is_finalizado:
            evolucao.marcar_finalizado()
        for doc in documentos:
            if is_finalizado:
                doc.marcar_finalizado()

        return ProntuarioResumoDTO(
            atendimento_id=atendimento_id,
            evolucao=evolucao,
            documentos=documentos,
            is_finalizado=is_finalizado,
        )

    async def obter_evolucao(self, atendimento_id: UUID) -> EvolucaoClinica:
        """Delegate SOAP evolution retrieval to EvolucaoService."""
        return await self._evolucao.obter_evolucao(atendimento_id)

    async def compilar_documento_pdf(self, documento_id: UUID) -> bytes:
        """Delegate PDF/A compilation to DocumentoService."""
        return await self._documentos.compilar_pdf(documento_id)

    async def assinar_documento_clinico(
        self,
        documento_id: UUID,
        atendimento_id: UUID,
        credenciais: DoctorCertificateCredentials,
    ) -> tuple[DocumentoClinico, bytes]:
        """Delegate ICP-Brasil PAdES signing to DocumentoService."""
        return await self._documentos.assinar(documento_id, atendimento_id, credenciais)
