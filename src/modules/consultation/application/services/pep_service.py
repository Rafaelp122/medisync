"""PEP clinical workflow service enforcing SOAP and Portaria 344/98 safeguards."""

import contextlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.audit import AtorPapel, AtorTipo, AuditTrailPort
from src.modules.consultation.application.dtos import (
    DocumentoAssinadoResult,
    EmitirDocumentoClinicoCommand,
    FinalizarConsultaCommand,
    ProntuarioResumoDTO,
    RegistrarEvolucaoSOAPCommand,
    TMAStatusDTO,
)
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoReaderPort,
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


class PEPService:
    """Application service for Electronic Health Record (PEP) and SOAP workflow."""

    def __init__(
        self,
        session: AsyncSession,
        pdf_generator: PDFGeneratorPort,
        signer: ICPBrasilSignerPort,
        storage: StoragePort,
        documento_service: DocumentoService,
        atendimento_reader: AtendimentoReaderPort | None = None,
        evolucao_service: EvolucaoService | None = None,
        audit_trail: AuditTrailPort | None = None,
    ) -> None:
        self._session = session
        self._pdf_generator = pdf_generator
        self._signer = signer
        self._storage = storage
        self._reader = atendimento_reader
        self._documentos = documento_service
        self._audit_trail = audit_trail
        self._evolucao = evolucao_service or EvolucaoService(
            session=session, reader=atendimento_reader, audit_trail=audit_trail
        )

    @property
    def storage(self) -> StoragePort:
        """Instância de StoragePort para binários de documentos sob ADR-006.

        Regras: docs/adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md.
        """
        return self._storage

    @property
    def documento_service(self) -> DocumentoService:
        """Serviço de ciclo de vida de documentos e assinatura digital.

        Regras: Portaria 344/98 e ADR-006.
        """
        return self._documentos

    @property
    def evolucao_service(self) -> EvolucaoService:
        """Serviço de registro de evolução clínica SOAP.

        Regras: RN06 (Ato Médico) e CFM nº 1.821/2007.
        """
        return self._evolucao

    @property
    def atendimento_reader(self) -> AtendimentoReaderPort | None:
        """Porta de leitura de atendimento para validação de terminalidade.

        Regras: RN06 e docs/explanation/domains/consultation-domain.md.
        """
        return self._reader

    async def _is_terminal(self, atendimento_id: UUID) -> bool:
        """Return True when queue-owned attendance reached terminal status."""
        return await is_atendimento_terminal(self._reader, atendimento_id)

    async def salvar_evolucao_soap(
        self, command: RegistrarEvolucaoSOAPCommand
    ) -> EvolucaoClinica:
        """Registra ou atualiza evolução SOAP com CID-10 e conduta médica.

        Garante soberania clínica e preenchimento sob CFM nº 2.314/2022.
        Regras: RN06 (Ato Médico) e docs/explanation/domains/consultation-domain.md.
        """
        return await self._evolucao.salvar_evolucao_soap(command)

    def validar_prescricao(self, medicamento: str) -> None:
        """Valida emissão digital de medicamento sob Portaria SVS/MS nº 344/98.

        Rejeita substâncias das Listas A/B que exigem talonário físico.
        Regras: Portaria 344/98 e docs/explanation/domains/consultation-domain.md.
        """
        validar_substancia_permitida_telemedicina(medicamento)

    async def emitir_documento(
        self, command: EmitirDocumentoClinicoCommand
    ) -> DocumentoClinico:
        """Delega emissão de documento clínico ao DocumentoService.

        Valida itens contra restrições sanitárias e gera chave canônica.
        Regras: Portaria 344/98 e ADR-006.
        """
        return await self._documentos.emitir_documento(command)

    async def compilar_pdf(self, documento_id: UUID) -> bytes:
        """Gera binário PDF/A-1b do documento com validação pública ITI.

        Garante conformidade com PAdES e CFM nº 2.314/2022 via DocumentoService.
        Regras: docs/adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md.
        """
        return await self._documentos.compilar_pdf(documento_id)

    async def assinar_documento(
        self,
        documento_id: UUID,
        atendimento_id: UUID,
        credenciais: DoctorCertificateCredentials,
    ) -> DocumentoAssinadoResult:
        """Assina documento clínico no padrão ICP-Brasil via Cloud PSC.

        Garante validade jurídica sob MP nº 2.200-2/2001 e CFM nº 2.314/2022.
        Regras: docs/adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md.
        """
        return await self._documentos.assinar(
            documento_id=documento_id,
            atendimento_id=atendimento_id,
            credenciais=credenciais,
        )

    async def finalizar_consulta(
        self, command: FinalizarConsultaCommand
    ) -> EvolucaoClinica:
        """Encerra a consulta clínica, bloqueando evolução SOAP e documentos.

        Assegura imutabilidade sob CFM nº 1.821/2007 e CFM nº 2.314/2022.
        Regras: RN06 (Ato Médico) e docs/explanation/domains/consultation-domain.md.
        """
        stmt = select(EvolucaoClinica).where(
            EvolucaoClinica.atendimento_id == command.atendimento_id
        )
        res = await self._session.execute(stmt)
        evolucao = res.scalar_one_or_none()

        if evolucao is None:
            raise ConsultaInvalidaError(
                f"Atendimento '{command.atendimento_id}' sem evolução preenchida. "
                "É obrigatório registrar a evolução SOAP antes da finalização."
            )

        is_term = await self._is_terminal(command.atendimento_id)
        if evolucao.is_finalizado or is_term:
            evolucao.marcar_finalizado()
            status_desc = "terminal" if is_term else "evolucao_finalizada"
            raise ConsultaFinalizadaError(
                f"A consulta '{command.atendimento_id}' já se encontra "
                f"finalizada e imutável (status atual: '{status_desc}')."
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

        with contextlib.suppress(Exception):
            if self._reader is not None:
                await self._reader.concluir_atendimento(command.atendimento_id)

        await self._session.flush()
        if self._audit_trail is not None:
            await self._audit_trail.record_event(
                organizacao_id=command.organizacao_id,
                tipo_evento="CONSULTA_FINALIZADA",
                ator_tipo=AtorTipo.PROFISSIONAL.value,
                ator_papel=AtorPapel.MEDICO.value,
                ator_id=command.medico_id,
                atendimento_id=command.atendimento_id,
                estado_anterior="EM_ATENDIMENTO",
                novo_estado="CONCLUIDO",
                payload={"evolucao_id": str(evolucao.id)},
            )
        await self._session.commit()
        return evolucao

    def calcular_tma_status(
        self,
        atendimento_id: UUID,
        iniciado_em: datetime | None = None,
        tma_planejado_segundos: int = 900,
    ) -> TMAStatusDTO:
        """Calcula telemetria de TMA preservando soberania do ato médico.

        Veda desconexão forçada ao estourar TMA, gerando aviso visual discreto.
        Regras: RN06 e docs/explanation/domains/consultation-domain.md.
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
        """Recupera visão unificada com evolução SOAP e documentos vinculados.

        Aplica bloqueio de integridade se atendimento encerrado (CFM 1.821/2007).
        Regras: RN06 e docs/explanation/domains/consultation-domain.md.
        """
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
        """Recupera evolução clínica SOAP persistida para o atendimento.

        Assegura acesso rastreável ao registro médico conforme CFM nº 1.821/2007.
        Regras: RN06 e docs/explanation/domains/consultation-domain.md.
        """
        return await self._evolucao.obter_evolucao(atendimento_id)
