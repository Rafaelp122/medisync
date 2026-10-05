"""PEP clinical workflow service enforcing SOAP and Portaria 344/98 safeguards."""

import contextlib
import re
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
from src.modules.consultation.domain.exceptions import (
    ConsultaFinalizadaError,
    ConsultaInvalidaError,
    EvolucaoNaoEncontradaError,
)
from src.modules.consultation.domain.models import (
    DocumentoClinico,
    EvolucaoClinica,
)
from src.modules.consultation.domain.models._substances import (
    validar_substancia_permitida_telemedicina,
)
from src.modules.consultation.domain.s3_keys import is_signed_document_key

_CID10_REGEX = re.compile(r"^[A-Z][0-9]{2}(\.[0-9]{1,2})?$")
_STATUS_TERMINAIS = frozenset({"CONCLUIDO", "PACIENTE_AUSENTE", "CANCELADO_PACIENTE"})


class PEPService:
    """Application service for Electronic Health Record (PEP) and SOAP workflow."""

    def __init__(
        self,
        session: AsyncSession,
        pdf_generator: PDFGeneratorPort,
        signer: ICPBrasilSignerPort,
        storage: StoragePort,
        documento_service: DocumentoService | None = None,
    ) -> None:
        self._session = session
        self._pdf_generator = pdf_generator
        self._signer = signer
        self._storage = storage
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

    @property
    def storage(self) -> StoragePort:
        """Return the injected storage port instance."""
        return self._storage

    @property
    def documento_service(self) -> DocumentoService:
        """Return the owned clinical document lifecycle service."""
        return self._documentos

    def is_documento_assinado(self, doc: DocumentoClinico) -> bool:
        """Deprecated: prefer DocumentoService.is_assinado (async, cache-aware)."""
        return is_signed_document_key(doc.chave_s3, doc.organizacao_id)

    async def _verificar_atendimento_finalizado(self, atendimento_id: UUID) -> bool:
        """Check whether the underlying attendance reached terminal status in DB."""
        try:
            status_stmt = text("SELECT status FROM atendimentos WHERE id = :atend_id")
            res = await self._session.execute(status_stmt, {"atend_id": atendimento_id})
            val = res.scalar_one_or_none()
            if val is not None:
                return str(val).strip().upper() in _STATUS_TERMINAIS
        except Exception:
            return False
        return False

    async def salvar_evolucao_soap(
        self, command: RegistrarEvolucaoSOAPCommand
    ) -> EvolucaoClinica:
        """Record or update SOAP clinical notes for an attendance."""
        stmt = select(EvolucaoClinica).where(
            EvolucaoClinica.atendimento_id == command.atendimento_id
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        is_term = await self._verificar_atendimento_finalizado(command.atendimento_id)

        if existing is not None:
            if existing.is_finalizado or is_term:
                existing.marcar_finalizado()
                raise ConsultaFinalizadaError(
                    "Não é permitido alterar evolução de consulta finalizada."
                )

            # Validate fields on update
            if not command.anamnese or not command.anamnese.strip():
                raise ConsultaInvalidaError(
                    "Anamnese clínica é obrigatória e não pode ser vazia."
                )
            if not command.conduta or not command.conduta.strip():
                raise ConsultaInvalidaError(
                    "Conduta clínica é obrigatória e não pode ser vazia."
                )

            clean_cid10: str | None = None
            if command.cid10_principal and command.cid10_principal.strip():
                c = command.cid10_principal.strip().upper()
                if not _CID10_REGEX.match(c):
                    raise ConsultaInvalidaError(
                        f"Código CID-10 inválido: '{command.cid10_principal}'. "
                        "Formato esperado: letra maiúscula seguida de 2 dígitos "
                        "e subcategoria opcional (ex.: J00, J02.9, A09.0)."
                    )
                clean_cid10 = c

            existing.anamnese = command.anamnese.strip()
            existing.conduta = command.conduta.strip()
            existing.exame_fisico_virtual = (
                command.exame_fisico_virtual.strip()
                if command.exame_fisico_virtual and command.exame_fisico_virtual.strip()
                else None
            )
            existing.cid10_principal = clean_cid10
            existing.registrado_em = datetime.now(UTC)

            await self._session.flush()
            await self._session.commit()
            return existing

        if is_term:
            raise ConsultaFinalizadaError(
                "Não é permitido criar evolução de consulta já finalizada."
            )

        evolucao = EvolucaoClinica(
            organizacao_id=command.organizacao_id,
            atendimento_id=command.atendimento_id,
            medico_id=command.medico_id,
            anamnese=command.anamnese,
            conduta=command.conduta,
            exame_fisico_virtual=command.exame_fisico_virtual,
            cid10_principal=command.cid10_principal,
        )
        self._session.add(evolucao)
        await self._session.flush()
        await self._session.commit()
        return evolucao

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

        is_term = await self._verificar_atendimento_finalizado(command.atendimento_id)
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

        # Update attendance status in database to CONCLUIDO
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

        is_term = await self._verificar_atendimento_finalizado(atendimento_id)
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
        """Return SOAP evolution or raise 404 EvolucaoNaoEncontradaError."""
        stmt = select(EvolucaoClinica).where(
            EvolucaoClinica.atendimento_id == atendimento_id
        )
        res = await self._session.execute(stmt)
        evolucao = res.scalar_one_or_none()
        if evolucao is None:
            raise EvolucaoNaoEncontradaError(
                "Nenhuma evolução clínica registrada para este atendimento."
            )
        return evolucao

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
