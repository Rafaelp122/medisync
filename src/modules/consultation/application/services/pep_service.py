"""Deep PEP clinical service owning SOAP, lifecycle, finalization and patient portal."""

import difflib
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.audit import AtorPapel, AtorTipo, AuditTrailPort
from src.core.errors import ForbiddenError, NotFoundError
from src.modules.consultation.application.dtos import (
    FinalizarConsultaCommand,
    FinalizarConsultaResult,
    HistoricoAtendimentoItemDTO,
    PacienteDocumentoItemDTO,
    ProntuarioResumoDTO,
    RegistrarEvolucaoSOAPCommand,
    TMAStatusDTO,
)
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoHistoricoDTO,
    AtendimentoReaderPort,
    AtendimentoResumoDTO,
    HistoricoAtendimentoReaderPort,
)
from src.modules.consultation.application.ports.producao_ambulatorial_port import (
    ProducaoAmbulatorialPort,
)
from src.modules.consultation.application.services.clinical_pdf_compiler import (
    ClinicalPdfCompiler,
)
from src.modules.consultation.domain.exceptions import (
    ConsultaFinalizadaError,
    ConsultaInvalidaError,
    DocumentoClinicoNaoEncontradoError,
    EvolucaoNaoEncontradaError,
    IANaoRatificadaError,
)
from src.modules.consultation.domain.models import (
    DocumentoClinico,
    EvolucaoClinica,
)

logger = logging.getLogger("medisync.consultation.pep")

_EPOCH_MIN_UTC = datetime.min.replace(tzinfo=UTC)
_STATUS_TERMINAIS = frozenset({"CONCLUIDO", "PACIENTE_AUSENTE", "CANCELADO_PACIENTE"})


def _is_resumo_terminal(resumo: AtendimentoResumoDTO | None) -> bool:
    """Determine terminal status from an already-loaded attendance summary."""
    if resumo is None:
        return False
    return bool(
        resumo.is_terminal or resumo.status.strip().upper() in _STATUS_TERMINAIS
    )


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
    """Deep module owning SOAP evolution, PEP summary, finalization and PDF view."""

    def __init__(
        self,
        session: AsyncSession,
        pdf_compiler: ClinicalPdfCompiler,
        atendimento_reader: AtendimentoReaderPort | None = None,
        audit_trail: AuditTrailPort | None = None,
        producao_port: ProducaoAmbulatorialPort | None = None,
    ) -> None:
        self._session = session
        self._pdf_compiler = pdf_compiler
        self._reader = atendimento_reader
        self._audit_trail = audit_trail
        self._producao_port = producao_port

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

    async def _obter_resumo(self, atendimento_id: UUID) -> AtendimentoResumoDTO | None:
        if self._reader is None:
            return None
        return await self._reader.obter_resumo(atendimento_id)

    async def _is_terminal(self, atendimento_id: UUID) -> bool:
        """Return True when queue-owned attendance reached terminal status."""
        return _is_resumo_terminal(await self._obter_resumo(atendimento_id))

    @staticmethod
    def _resolver_diff_ia(command: RegistrarEvolucaoSOAPCommand) -> str | None:
        """Calcula o diff da sugestão de IA versus a conduta médica ratificada.

        Regras: CFM nº 2.454/2026 e docs/explanation/domains/consultation-domain.md.
        """
        if not command.ia_utilizada:
            return None
        if not command.ia_ratificada_pelo_medico:
            conduta_preview = command.conduta[:40].replace("\n", " ")
            raise IANaoRatificadaError(
                f"Sugestão de IA para o plano SOAP '{conduta_preview}...' não foi "
                f"ratificada pelo médico assistente '{command.medico_id}' conforme "
                "Resolução CFM nº 2.454/2026."
            )
        diff = command.ia_diff_modificacao
        if (
            not diff
            and command.ia_sugestao_bruta
            and command.ia_sugestao_bruta != command.conduta
        ):
            diff_lines = list(
                difflib.unified_diff(
                    command.ia_sugestao_bruta.splitlines(keepends=True),
                    command.conduta.splitlines(keepends=True),
                    fromfile="sugestao_ia",
                    tofile="plano_ratificado",
                )
            )
            diff = "".join(diff_lines)
        return diff

    async def _registrar_auditoria_soap(
        self,
        command: RegistrarEvolucaoSOAPCommand,
        evolucao: EvolucaoClinica,
        diff_ia: str | None,
    ) -> None:
        if self._audit_trail is None:
            return
        await self._audit_trail.record_event(
            tipo_evento="EVOLUCAO_SOAP_REGISTRADA",
            ator_tipo=AtorTipo.PROFISSIONAL.value,
            ator_papel=AtorPapel.MEDICO.value,
            ator_id=command.medico_id,
            atendimento_id=command.atendimento_id,
            payload={
                "evolucao_id": str(evolucao.id),
                "cid10": evolucao.cid10_principal,
                "codigo_sigtap": evolucao.codigo_sigtap,
                "ia_utilizada": evolucao.ia_utilizada,
            },
        )
        if command.ia_utilizada:
            await self._audit_trail.record_event(
                tipo_evento="IA_DECISAO_MEDICA_REGISTRADA",
                ator_tipo=AtorTipo.PROFISSIONAL.value,
                ator_papel=AtorPapel.MEDICO.value,
                ator_id=command.medico_id,
                atendimento_id=command.atendimento_id,
                payload={
                    "evolucao_id": str(evolucao.id),
                    "ia_modelo": command.ia_modelo,
                    "ia_ratificada": command.ia_ratificada_pelo_medico,
                    "diff_forense": diff_ia,
                },
            )

    @staticmethod
    def _aplicar_atualizacao_soap(
        evolucao: EvolucaoClinica,
        command: RegistrarEvolucaoSOAPCommand,
        diff_ia: str | None,
        *,
        is_term: bool,
    ) -> None:
        if evolucao.is_finalizado or is_term:
            evolucao.marcar_finalizado()
            status_desc = "terminal" if is_term else "evolucao_finalizada"
            raise ConsultaFinalizadaError(
                "Não é permitido alterar evolução de consulta finalizada "
                f"(status atual: '{status_desc}')."
            )
        evolucao.atualizar_soap(
            anamnese=command.anamnese,
            conduta=command.conduta,
            exame_fisico_virtual=command.exame_fisico_virtual,
            cid10_principal=command.cid10_principal,
            codigo_sigtap=command.codigo_sigtap,
            ia_utilizada=command.ia_utilizada,
            ia_modelo=command.ia_modelo,
            ia_sugestao_bruta=command.ia_sugestao_bruta,
            ia_diff_modificacao=diff_ia,
            ia_ratificada_pelo_medico=command.ia_ratificada_pelo_medico,
            identidade_verificada=command.identidade_verificada,
            tipo_documento_verificado=command.tipo_documento_verificado,
            justificativa_excecao_identidade=command.justificativa_excecao_identidade,
        )

    async def _buscar_evolucao_opcional(
        self, atendimento_id: UUID
    ) -> EvolucaoClinica | None:
        stmt = select(EvolucaoClinica).where(
            EvolucaoClinica.atendimento_id == atendimento_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def salvar_evolucao_soap(
        self, command: RegistrarEvolucaoSOAPCommand
    ) -> EvolucaoClinica:
        """Registra ou atualiza evolução SOAP com governança de IA.

        Garante soberania clínica e preenchimento sob CFM nº 1.821/2007,
        2.314/2022 e 2.454/2026. Regras: RN06 e
        docs/explanation/domains/consultation-domain.md.
        """
        diff_ia = self._resolver_diff_ia(command)
        existing = await self._buscar_evolucao_opcional(command.atendimento_id)
        is_term = await self._is_terminal(command.atendimento_id)

        if existing is not None:
            self._aplicar_atualizacao_soap(existing, command, diff_ia, is_term=is_term)
            await self._session.flush()
            await self._registrar_auditoria_soap(command, existing, diff_ia)
            await self._session.commit()
            return existing

        if is_term:
            raise ConsultaFinalizadaError(
                "Não é permitido criar evolução de consulta já finalizada "
                f"(atendimento '{command.atendimento_id}')."
            )

        evolucao = EvolucaoClinica(
            atendimento_id=command.atendimento_id,
            medico_id=command.medico_id,
            anamnese=command.anamnese,
            conduta=command.conduta,
            exame_fisico_virtual=command.exame_fisico_virtual,
            cid10_principal=command.cid10_principal,
            codigo_sigtap=command.codigo_sigtap,
            ia_utilizada=command.ia_utilizada,
            ia_modelo=command.ia_modelo,
            ia_sugestao_bruta=command.ia_sugestao_bruta,
            ia_diff_modificacao=diff_ia,
            ia_ratificada_pelo_medico=command.ia_ratificada_pelo_medico,
            identidade_verificada=command.identidade_verificada,
            tipo_documento_verificado=command.tipo_documento_verificado,
            justificativa_excecao_identidade=command.justificativa_excecao_identidade,
        )
        self._session.add(evolucao)
        try:
            await self._session.flush()
        except IntegrityError:
            await self._session.rollback()
            existing_retry = await self._buscar_evolucao_opcional(
                command.atendimento_id
            )
            if existing_retry is None:
                raise
            self._aplicar_atualizacao_soap(
                existing_retry, command, diff_ia, is_term=is_term
            )
            await self._session.flush()
            await self._registrar_auditoria_soap(command, existing_retry, diff_ia)
            await self._session.commit()
            return existing_retry

        await self._registrar_auditoria_soap(command, evolucao, diff_ia)
        await self._session.commit()
        return evolucao

    async def obter_evolucao(self, atendimento_id: UUID) -> EvolucaoClinica:
        """Recupera evolução clínica SOAP persistida para o atendimento.

        Garante integridade e rastreabilidade conforme CFM nº 1.821/2007.
        Regras: RN06 e docs/explanation/domains/consultation-domain.md.
        """
        evolucao = await self._buscar_evolucao_opcional(atendimento_id)
        if evolucao is None:
            raise EvolucaoNaoEncontradaError(
                f"Nenhuma evolução clínica registrada para o atendimento "
                f"'{atendimento_id}'."
            )
        return evolucao

    async def compilar_pdf(
        self,
        documento_id: UUID,
        *,
        atendimento_id: UUID | None = None,
    ) -> bytes:
        """Compila binário PDF/A-1b do documento validando posse do atendimento.

        Impede IDOR horizontal delegando ao ClinicalPdfCompiler compartilhado.
        Regras: CFM nº 2.314/2022 e
        docs/adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md.
        """
        return await self._pdf_compiler.compilar(
            documento_id, atendimento_id=atendimento_id
        )

    async def _consolidar_ambulatorio_em_savepoint(
        self,
        command: FinalizarConsultaCommand,
        paciente_id: UUID,
        codigo_sigtap: str,
    ) -> None:
        if self._producao_port is None:
            return
        try:
            async with self._session.begin_nested():
                await self._producao_port.consolidar_teleconsulta(
                    atendimento_id=command.atendimento_id,
                    profissional_id=command.medico_id,
                    paciente_id=paciente_id,
                    codigo_sigtap=codigo_sigtap,
                )
        except Exception as exc:
            logger.warning(
                "Falha ao consolidar teleconsulta ambulatorial (BPA-I/SUS) "
                "para atendimento '%s' (médico: %s, paciente: %s, "
                "sigtap: '%s'): %s",
                command.atendimento_id,
                command.medico_id,
                paciente_id,
                codigo_sigtap,
                exc,
                exc_info=True,
            )

    async def _obter_resumo_resiliente(
        self, atendimento_id: UUID
    ) -> AtendimentoResumoDTO | None:
        if self._reader is None:
            return None
        try:
            return await self._reader.obter_resumo(atendimento_id)
        except Exception as exc:
            logger.warning(
                "Falha ao obter resumo do atendimento '%s' via reader: %s",
                atendimento_id,
                exc,
                exc_info=True,
            )
            return None

    async def finalizar_consulta(
        self, command: FinalizarConsultaCommand
    ) -> FinalizarConsultaResult:
        """Encerra a consulta clínica com commit único atômico e savepoints.

        Assegura imutabilidade sob CFM nº 1.821/2007 e CFM nº 2.314/2022.
        Regras: RN06 (Ato Médico) e docs/explanation/domains/consultation-domain.md.
        """
        evolucao = await self._buscar_evolucao_opcional(command.atendimento_id)
        if evolucao is None:
            raise ConsultaInvalidaError(
                f"Atendimento '{command.atendimento_id}' sem evolução preenchida. "
                "É obrigatório registrar a evolução SOAP antes da finalização."
            )

        resumo = await self._obter_resumo_resiliente(command.atendimento_id)
        is_term = _is_resumo_terminal(resumo)
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

        doc_stmt = select(DocumentoClinico).where(
            DocumentoClinico.atendimento_id == command.atendimento_id
        )
        doc_res = await self._session.execute(doc_stmt)
        for doc in doc_res.scalars().all():
            doc.marcar_finalizado()

        medico_para_liberar = await self._concluir_fila_antes_commit(
            command.atendimento_id
        )

        if resumo is not None and resumo.paciente_id is not None:
            await self._consolidar_ambulatorio_em_savepoint(
                command, resumo.paciente_id, evolucao.codigo_sigtap
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
        await self._liberar_lock_consulta_pos_commit(medico_para_liberar)
        return FinalizarConsultaResult(
            atendimento_id=command.atendimento_id,
            is_finalizado=evolucao.is_finalizado,
        )

    async def _concluir_fila_antes_commit(self, atendimento_id: UUID) -> UUID | None:
        if self._reader is None:
            return None
        try:
            async with self._session.begin_nested():
                return await self._reader.concluir_atendimento(
                    atendimento_id,
                    auto_commit=False,
                )
        except Exception as exc:
            logger.warning(
                "Falha ao concluir atendimento '%s' na fila virtual via reader: %s",
                atendimento_id,
                exc,
                exc_info=True,
            )
            return None

    async def _liberar_lock_consulta_pos_commit(self, medico_id: UUID | None) -> None:
        if self._reader is None or medico_id is None:
            return
        try:
            await self._reader.liberar_consulta_ativa_medico(medico_id)
        except Exception as exc:
            logger.warning(
                "Falha ao liberar lock de consulta ativa para médico '%s' "
                "pós-commit: %s",
                medico_id,
                exc,
                exc_info=True,
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
        evolucao = await self._buscar_evolucao_opcional(atendimento_id)

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
        if is_finalizado:
            for doc in documentos:
                doc.marcar_finalizado()

        return ProntuarioResumoDTO(
            atendimento_id=atendimento_id,
            evolucao=evolucao,
            documentos=documentos,
            is_finalizado=is_finalizado,
        )

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
        return await self.compilar_pdf(documento_id, atendimento_id=doc.atendimento_id)
