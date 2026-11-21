"""PEP clinical workflow service enforcing SOAP and Portaria 344/98 safeguards."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.audit import AtorPapel, AtorTipo, AuditTrailPort
from src.core.errors import ForbiddenError, NotFoundError
from src.modules.consultation.application.dtos import (
    DocumentoAssinadoResult,
    EmitirDocumentoClinicoCommand,
    FinalizarConsultaCommand,
    FinalizarConsultaResult,
    HistoricoAtendimentoItemDTO,
    PacienteDocumentoItemDTO,
    ProntuarioResumoDTO,
    RegistrarEvolucaoSOAPCommand,
    TMAStatusDTO,
    VerificarLivenessCommand,
)
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoHistoricoDTO,
    AtendimentoReaderPort,
    AtendimentoResumoDTO,
    HistoricoAtendimentoReaderPort,
    is_atendimento_terminal,
)
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
    ICPBrasilSignerPort,
)
from src.modules.consultation.application.ports.liveness_verification_port import (
    LivenessChallengeDTO,
    LivenessVerificationResultDTO,
)
from src.modules.consultation.application.ports.pdf_generator_port import (
    PDFGeneratorPort,
)
from src.modules.consultation.application.ports.producao_ambulatorial_port import (
    ProducaoAmbulatorialPort,
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
    DocumentoClinicoNaoEncontradoError,
)
from src.modules.consultation.domain.models import (
    DocumentoClinico,
    EvolucaoClinica,
)
from src.modules.consultation.domain.models._substances import (
    validar_substancia_permitida_telemedicina,
)

logger = logging.getLogger("medisync.consultation.pep")

_EPOCH_MIN_UTC = datetime.min.replace(tzinfo=UTC)


def _extrair_criado_em_documento(
    doc: DocumentoClinico,
    atendimento_criado_em: datetime | None,
) -> datetime | None:
    if doc.id.version == 7:
        timestamp_ms = int.from_bytes(doc.id.bytes[:6], "big")
        return datetime.fromtimestamp(timestamp_ms / 1000.0, tz=UTC)
    return doc.assinado_em or doc.finalizado_em or atendimento_criado_em


def _montar_historico_item(
    item: AtendimentoHistoricoDTO,
    evolucao: EvolucaoClinica | None,
) -> HistoricoAtendimentoItemDTO:
    finalizada = evolucao is not None and evolucao.is_finalizado
    diagnostico = (
        evolucao.cid10_principal if evolucao is not None and finalizada else None
    )
    conduta = evolucao.conduta if evolucao is not None and finalizada else None
    finalizado_em = item.finalizado_em or (
        evolucao.finalizado_em if evolucao is not None and finalizada else None
    )
    return HistoricoAtendimentoItemDTO(
        atendimento_id=item.atendimento_id,
        status=item.status,
        prioridade_clinica=item.prioridade_clinica,
        queixa_principal=item.queixa_principal,
        criado_em=item.criado_em,
        finalizado_em=finalizado_em,
        medico_id=item.medico_id,
        diagnostico_cid10=diagnostico,
        conduta_resumo=conduta,
    )


def _montar_paciente_documento_dto(
    doc: DocumentoClinico,
    atendimento_criado_em: datetime | None,
) -> PacienteDocumentoItemDTO:
    status_assinatura = "ASSINADO" if doc.assinado_em is not None else "EMITIDO"
    return PacienteDocumentoItemDTO(
        documento_id=doc.id,
        atendimento_id=doc.atendimento_id,
        tipo_documento=str(doc.tipo_documento),
        status_assinatura=status_assinatura,
        token_validacao=str(doc.id),
        criado_em=_extrair_criado_em_documento(doc, atendimento_criado_em),
        assinado_em=doc.assinado_em,
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
        producao_port: ProducaoAmbulatorialPort | None = None,
    ) -> None:
        self._session = session
        self._pdf_generator = pdf_generator
        self._signer = signer
        self._storage = storage
        self._reader = atendimento_reader
        self._documentos = documento_service
        self._audit_trail = audit_trail
        self._producao_port = producao_port
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

    @property
    def producao_port(self) -> ProducaoAmbulatorialPort | None:
        """Porta para consolidação ambulatorial BPA-I (SUS ADR-012).

        Regras: US-11 e ADR-012 (Consolidação Ambulatorial SUS BPA-I).
        """
        return self._producao_port

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

    async def solicitar_desafio_liveness(
        self, atendimento_id: UUID
    ) -> LivenessChallengeDTO:
        """Delega geração de desafio facial (US-15) ao DocumentoService.

        Regras: RF-07 e docs/user-stories/US-15-prova-de-vida-facial-liveness.md.
        """
        return await self._documentos.solicitar_desafio_liveness(atendimento_id)

    async def verificar_liveness_prescricao(
        self, command: VerificarLivenessCommand
    ) -> LivenessVerificationResultDTO:
        """Delega verificação de prova de vida facial (US-15) ao DocumentoService.

        Regras: RF-07 e docs/user-stories/US-15-prova-de-vida-facial-liveness.md.
        """
        return await self._documentos.verificar_liveness_prescricao(command)

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
    ) -> FinalizarConsultaResult:
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

        if not evolucao.identidade_verificada:
            raise ConsultaInvalidaError(
                f"Atendimento '{command.atendimento_id}' bloqueado pela Resolução "
                "CFM nº 2.314/2022: identidade_verificada=False; é obrigatória a "
                "conferência visual do documento oficial do paciente antes de "
                "finalizar a consulta."
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

        resumo: AtendimentoResumoDTO | None = None
        if self._reader is not None:
            try:
                resumo = await self._reader.obter_resumo(command.atendimento_id)
            except Exception as exc:
                logger.warning(
                    "Falha ao obter resumo do atendimento '%s' via reader: %s",
                    command.atendimento_id,
                    exc,
                    exc_info=True,
                )
            try:
                await self._reader.concluir_atendimento(command.atendimento_id)
            except Exception as exc:
                logger.warning(
                    "Falha ao concluir atendimento '%s' na fila virtual via reader: %s",
                    command.atendimento_id,
                    exc,
                    exc_info=True,
                )

        if (
            self._producao_port is not None
            and resumo is not None
            and resumo.paciente_id is not None
        ):
            try:
                await self._producao_port.consolidar_teleconsulta(
                    atendimento_id=command.atendimento_id,
                    profissional_id=command.medico_id,
                    paciente_id=resumo.paciente_id,
                    codigo_sigtap=evolucao.codigo_sigtap,
                )
            except Exception as exc:
                logger.warning(
                    "Falha ao consolidar teleconsulta ambulatorial (BPA-I/SUS) "
                    "para atendimento '%s' (médico: %s, paciente: %s, "
                    "sigtap: '%s'): %s",
                    command.atendimento_id,
                    command.medico_id,
                    resumo.paciente_id,
                    evolucao.codigo_sigtap,
                    exc,
                    exc_info=True,
                )

        await self._session.flush()
        if self._audit_trail is not None:
            await self._audit_trail.record_event(
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
        return FinalizarConsultaResult(
            atendimento_id=command.atendimento_id,
            is_finalizado=evolucao.is_finalizado,
        )

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

    async def _listar_atendimentos_paciente(
        self,
        paciente_id: UUID,
    ) -> list[AtendimentoHistoricoDTO]:
        if isinstance(self._reader, HistoricoAtendimentoReaderPort):
            return await self._reader.listar_historico_paciente(paciente_id)
        raise RuntimeError(
            "HistoricoAtendimentoReaderPort não configurado em PEPService para "
            f"consultar histórico do paciente '{paciente_id}' "
            f"(reader atual: '{type(self._reader).__name__}')."
        )

    async def _validar_titularidade_documento(
        self,
        doc: DocumentoClinico,
        paciente_id: UUID,
    ) -> None:
        if self._reader is None:
            raise RuntimeError(
                "AtendimentoReaderPort não configurado em PEPService para "
                f"validar titularidade do documento '{doc.id}'."
            )

        resumo = await self._reader.obter_resumo(doc.atendimento_id)
        if resumo is None:
            raise NotFoundError(
                f"Atendimento '{doc.atendimento_id}' vinculado ao documento "
                f"'{doc.id}' não encontrado para o paciente '{paciente_id}'."
            )
        if resumo.paciente_id != paciente_id:
            raise ForbiddenError(
                f"Acesso negado ao documento '{doc.id}': paciente '{paciente_id}' "
                f"não é o titular do atendimento '{doc.atendimento_id}'."
            )

    async def listar_historico_paciente(
        self,
        paciente_id: UUID,
    ) -> list[HistoricoAtendimentoItemDTO]:
        """Lista histórico de consultas do paciente com resumo SOAP finalizado.

        Assegura isolamento Anti-IDOR e veda vazamento de rascunhos em aberto.
        Regras: LGPD Art. 18, CFM nº 1.821/2007 e
        docs/explanation/domains/consultation-domain.md.
        """
        atendimentos = await self._listar_atendimentos_paciente(paciente_id)
        if not atendimentos:
            return []

        atendimento_ids = [item.atendimento_id for item in atendimentos]
        stmt = select(EvolucaoClinica).where(
            EvolucaoClinica.atendimento_id.in_(atendimento_ids),
            EvolucaoClinica.finalizado_em.is_not(None),
        )
        res = await self._session.execute(stmt)
        evolucoes = {
            ev.atendimento_id: ev for ev in res.scalars().all() if ev.is_finalizado
        }
        return [
            _montar_historico_item(item, evolucoes.get(item.atendimento_id))
            for item in atendimentos
        ]

    async def listar_documentos_paciente(
        self,
        paciente_id: UUID,
    ) -> list[PacienteDocumentoItemDTO]:
        """Lista documentos do paciente ordenados do mais recente ao mais antigo.

        Omite chaves internas S3 e aplica isolamento estrito por titularidade.
        Regras: LGPD Art. 18, CFM nº 2.314/2022 e
        docs/adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md.
        """
        atendimentos = await self._listar_atendimentos_paciente(paciente_id)
        if not atendimentos:
            return []

        atendimento_map = {item.atendimento_id: item for item in atendimentos}
        stmt = (
            select(DocumentoClinico)
            .where(
                DocumentoClinico.atendimento_id.in_(list(atendimento_map.keys())),
            )
            .order_by(
                DocumentoClinico.assinado_em.desc().nullslast(),
                DocumentoClinico.id.desc(),
            )
        )
        res = await self._session.execute(stmt)
        items = [
            _montar_paciente_documento_dto(
                doc, atendimento_map[doc.atendimento_id].criado_em
            )
            for doc in res.scalars().all()
            if doc.atendimento_id in atendimento_map
        ]
        items.sort(
            key=lambda d: (
                d.criado_em or _EPOCH_MIN_UTC,
                d.assinado_em or _EPOCH_MIN_UTC,
                str(d.documento_id),
            ),
            reverse=True,
        )
        return items

    async def compilar_pdf_para_paciente(
        self,
        documento_id: UUID,
        paciente_id: UUID,
    ) -> bytes:
        """Compila PDF/A de documento clínico após validar titularidade do paciente.

        Bloqueia acesso cruzado entre pacientes por titularidade estrita (Anti-IDOR).
        Regras: LGPD Art. 18, CFM nº 2.314/2022 e
        docs/adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md.
        """
        stmt = select(DocumentoClinico).where(DocumentoClinico.id == documento_id)
        res = await self._session.execute(stmt)
        doc = res.scalar_one_or_none()
        if doc is None:
            raise DocumentoClinicoNaoEncontradoError(
                f"Documento clínico '{documento_id}' não encontrado "
                f"para o paciente '{paciente_id}'."
            )

        await self._validar_titularidade_documento(doc, paciente_id)
        return await self.compilar_pdf(documento_id)
