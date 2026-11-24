"""Queue ingestion, 64-bit priority scoring, and acquisition service (RN01)."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from arq.connections import ArqRedis
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import AtorPapel, AtorTipo, AuditTrailPort
from src.core.errors import ValidationError
from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoCommand,
    AdmissaoAtendimentoResult,
    AdquirirProximoPacienteCommand,
    AlocacaoChamadaResult,
    AvaliarAdmissaoCommand,
    CancelarAtendimentoResult,
    IngressarFilaCommand,
    IngressarFilaResult,
    PioraClinicaInput,
    PioraClinicaResult,
    PosicaoFilaResult,
    RegularizacaoFilaCommand,
    RegularizacaoFilaResult,
)
from src.modules.queue.application.ports.paciente_ausente_notifier import (
    LoggingPacienteAusenteNotifier,
    PacienteAusenteEvent,
    PacienteAusenteNotifierPort,
)
from src.modules.queue.application.ports.queue_engine_port import QueueEnginePort
from src.modules.queue.application.ports.queue_store_port import (
    AdmissaoAptoResult,
    AtendimentoHistoricoQueueDTO,
    AtendimentoSnapshotDTO,
)
from src.modules.queue.application.ports.shift_policy_reader_port import (
    ShiftPolicyDTO,
    ShiftPolicyReaderPort,
)
from src.modules.queue.application.ports.triage_port import (
    TriageEvaluationDTO,
    TriagePort,
)
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.application.services.controle_admissao_service import (
    MENSAGEM_COTA_ATINGIDA,
    ControleAdmissaoService,
)
from src.modules.queue.domain.exceptions import (
    AdmissaoFilaSuspensaError,
    AtendimentoNaoEncontradoError,
    TransicaoEstadoInvalidaError,
)
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import (
    TERMINAL_STATUSES,
    StatusAtendimento,
)
from src.modules.queue.domain.scoring import calcular_score

logger = logging.getLogger("medisync.queue.fila")

_INSTRUCOES_SAMU_FALLBACK = (
    "Sinais de gravidade identificados. Ligue 192 imediatamente "
    "ou procure a emergência mais próxima."
)


def _safe_tcle_hash(atendimento: Atendimento) -> str | None:
    val = getattr(atendimento, "tcle_hash", None)
    return val if isinstance(val, str) else None


class FilaService:
    """Gerencia admissão com backpressure, ordenação e aquisição de pacientes.

    Aplica score 64-bit (RN01), Lua 4-Keys/45s (RN02) e backpressure (RN05).
    Regras: docs/explanation/domains/queue-domain.md
    ADR: docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md
    História: docs/user-stories/US-07-alocacao-chamada-medica.md
    """

    def __init__(
        self,
        queue_engine: QueueEnginePort,
        db_session: AsyncSession,
        alocacao_service: AlocacaoChamadaService | None = None,
        controle_admissao: ControleAdmissaoService | None = None,
        triage_port: TriagePort | None = None,
        shift_policy_reader: ShiftPolicyReaderPort | None = None,
        arq_pool: ArqRedis | None = None,
        audit_trail: AuditTrailPort | None = None,
    ) -> None:
        self._queue_engine = queue_engine
        self._db_session = db_session
        self._alocacao_service = alocacao_service
        self._controle_admissao = controle_admissao or ControleAdmissaoService(
            queue_engine=queue_engine
        )
        self._triage_port = triage_port
        self._shift_policy_reader = shift_policy_reader
        self._arq_pool = arq_pool
        self._audit_trail: AuditTrailPort | None = audit_trail

    @property
    def controle_admissao(self) -> ControleAdmissaoService:
        """Retorna serviço de controle de admissão estocástica (RN05)."""
        return self._controle_admissao

    @property
    def arq_pool(self) -> ArqRedis | None:
        """Retorna pool ARQ configurado para jobs assíncronos (ADR-004)."""
        return self._arq_pool

    @property
    def triage_port(self) -> TriagePort | None:
        """Retorna porta de triagem clínica configurada (ADR-001)."""
        return self._triage_port

    async def _obter_politica_plantao(self) -> ShiftPolicyDTO:
        if self._shift_policy_reader is None:
            return ShiftPolicyDTO()
        return await self._shift_policy_reader.obter_politica_atual()

    async def admitir_paciente(
        self,
        command: AdmissaoAtendimentoCommand,
        *,
        raise_on_emergency: bool = True,
    ) -> AdmissaoAtendimentoResult:
        """Executa fluxo completo de admissão clínica (RN01, RN04, RN05, RN07).

        Valida risco e TCLE, lê presença real e política do plantão, reserva cota
        diária atomicamente no Valkey e só insere no ZSET após commit no Postgres.
        Regras: docs/explanation/domains/queue-domain.md
        """
        if self._triage_port is None:
            raise RuntimeError(
                "TriagePort não configurado no FilaService para admissão "
                f"do paciente '{command.paciente_id}'."
            )

        triage_eval = await self._triage_port.avaliar_risco(
            queixa_principal=command.queixa_principal,
            sintomas=command.sintomas,
            escala_dor=command.escala_dor,
            tcle_texto=command.tcle_texto,
            tcle_hash=command.tcle_hash,
            raise_on_emergency=raise_on_emergency,
        )

        policy = await self._obter_politica_plantao()
        medicos_ativos = await self._queue_engine.obter_medicos_ativos_count()
        tma = (
            command.tma_estimado_segundos
            if command.tma_estimado_segundos is not None
            else policy.tma_padrao_segundos
        )
        alpha = (
            command.alpha_margem
            if command.alpha_margem is not None
            else policy.alpha_backpressure
        )
        cota_max = (
            command.cota_diaria_maxima
            if command.cota_diaria_maxima is not None
            else policy.cota_diaria_maxima
        )

        if medicos_ativos <= 0:
            await self._bloquear_sem_medicos(
                tempo_restante_segundos=command.tempo_restante_segundos,
                tma=tma,
                alpha=alpha,
                cota_max=cota_max,
            )

        permitido, total_apos = await self._queue_engine.consumir_cota_ou_bloquear(
            cota_max
        )
        if not permitido:
            logger.warning(
                "Daily admission quota exhausted (cap=%s, active_doctors=%d)",
                cota_max,
                medicos_ativos,
            )
            raise AdmissaoFilaSuspensaError(
                detail=MENSAGEM_COTA_ATINGIDA,
                motivo="COTA_ATINGIDA",
            )

        return await self._executar_persistencia_admissao(
            command=command,
            triage_port=self._triage_port,
            triage_eval=triage_eval,
            medicos_ativos=medicos_ativos,
            total_antes_reserva=max(0, total_apos - 1),
            tma=tma,
            alpha=alpha,
            cota_max=cota_max,
        )

    async def _bloquear_sem_medicos(
        self,
        *,
        tempo_restante_segundos: float,
        tma: int,
        alpha: float,
        cota_max: int | None,
    ) -> None:
        avaliacao = await self._controle_admissao.avaliar_admissao(
            AvaliarAdmissaoCommand(
                medicos_ativos=0,
                tempo_restante_segundos=tempo_restante_segundos,
                pacientes_aguardando=0,
                total_admissoes_hoje=0,
                tma_estimado_segundos=tma,
                alpha_margem=alpha,
                cota_diaria_maxima=cota_max,
            )
        )
        raise AdmissaoFilaSuspensaError(
            detail=avaliacao.mensagem_explicativa,
            motivo=avaliacao.motivo_bloqueio or "SEM_MEDICOS_ATIVOS",
        )

    async def _executar_persistencia_admissao(
        self,
        *,
        command: AdmissaoAtendimentoCommand,
        triage_port: TriagePort,
        triage_eval: TriageEvaluationDTO,
        medicos_ativos: int,
        total_antes_reserva: int,
        tma: int,
        alpha: float,
        cota_max: int | None,
    ) -> AdmissaoAtendimentoResult:
        now = datetime.now(UTC)
        try:
            pacientes_aguardando = await self._queue_engine.obter_tamanho_fila()
            avaliacao = await self._controle_admissao.avaliar_admissao(
                AvaliarAdmissaoCommand(
                    medicos_ativos=medicos_ativos,
                    tempo_restante_segundos=command.tempo_restante_segundos,
                    pacientes_aguardando=pacientes_aguardando,
                    total_admissoes_hoje=total_antes_reserva,
                    tma_estimado_segundos=tma,
                    alpha_margem=alpha,
                    cota_diaria_maxima=cota_max,
                )
            )
            if not avaliacao.admissao_permitida:
                motivo = avaliacao.motivo_bloqueio or "CAPACIDADE_EXCEDIDA"
                raise AdmissaoFilaSuspensaError(
                    detail=avaliacao.mensagem_explicativa,
                    motivo=motivo,
                )

            atendimento = Atendimento(
                paciente_id=command.paciente_id,
                prioridade_clinica=triage_eval.prioridade_clinica,
                tcle_hash=triage_eval.tcle_hash,
                status=StatusAtendimento.APTO_PARA_CHAMADA,
                data_entrada_fila=now,
            )
            self._db_session.add(atendimento)
            await self._db_session.flush()

            triagem_id = await triage_port.registrar_triagem(
                atendimento_id=atendimento.id,
                queixa_principal=command.queixa_principal,
                sintomas=command.sintomas,
                prioridade_calculada=triage_eval.prioridade_clinica,
                alerta_samu_disparado=triage_eval.alerta_samu_disparado,
                escala_dor=command.escala_dor,
            )

            atendimento_id = atendimento.id
            status_atendimento = str(atendimento.status)

            await self._registrar_auditoria_admissao(
                atendimento_id=atendimento_id,
                paciente_id=command.paciente_id,
                status_atendimento=status_atendimento,
                triage_eval=triage_eval,
                triagem_id=triagem_id,
                ip_origem=command.ip_origem,
            )

            await self._db_session.commit()
        except Exception:
            await self._db_session.rollback()
            await self._queue_engine.estornar_cota_diaria()
            raise

        score = calcular_score(triage_eval.prioridade_clinica, now)
        await self._queue_engine.inserir_ou_atualizar_fila(atendimento_id, score)

        logger.info(
            "Patient %s admitted to SUS queue (status=%s, score=%d)",
            command.paciente_id,
            status_atendimento,
            score,
        )
        return AdmissaoAtendimentoResult(
            atendimento_id=atendimento_id,
            triagem_id=triagem_id,
            paciente_id=command.paciente_id,
            status_atendimento=status_atendimento,
            prioridade_clinica=triage_eval.prioridade_clinica,
            alerta_samu_disparado=triage_eval.alerta_samu_disparado,
            instrucoes=triage_eval.instrucao_redirecionamento,
            tcle_hash=triage_eval.tcle_hash,
        )

    async def _registrar_auditoria_admissao(
        self,
        *,
        atendimento_id: UUID,
        paciente_id: UUID,
        status_atendimento: str,
        triage_eval: TriageEvaluationDTO,
        triagem_id: UUID,
        ip_origem: str | None,
    ) -> None:
        if self._audit_trail is None:
            return
        await self._audit_trail.record_event(
            atendimento_id=atendimento_id,
            ator_tipo=AtorTipo.PACIENTE,
            ator_papel=AtorPapel.PACIENTE,
            tipo_evento="ADMISSAO_PACIENTE",
            ator_id=paciente_id,
            estado_anterior=None,
            novo_estado=status_atendimento,
            tcle_hash=triage_eval.tcle_hash,
            payload={
                "prioridade_clinica": triage_eval.prioridade_clinica,
                "triagem_id": str(triagem_id),
            },
            ip_origem=ip_origem,
        )

    async def ingressar_fila(
        self,
        command: IngressarFilaCommand,
    ) -> IngressarFilaResult:
        """Insere atendimento apto na fila virtual ordenada por score 64-bit (RN01).

        Regras: docs/explanation/domains/queue-domain.md
        """
        score = calcular_score(
            command.prioridade_clinica,
            command.data_entrada_fila,
        )
        rank = await self._queue_engine.inserir_ou_atualizar_fila(
            command.atendimento_id, score
        )
        posicao = (rank + 1) if rank is not None else 1

        logger.info(
            "Attendance %s ingested into queue with score=%d (pos=%d)",
            command.atendimento_id,
            score,
            posicao,
        )
        return IngressarFilaResult(
            atendimento_id=command.atendimento_id,
            score=score,
            posicao=posicao,
        )

    async def adquirir_proximo_paciente(
        self,
        command: AdquirirProximoPacienteCommand,
    ) -> AlocacaoChamadaResult | None:
        """Adquire atomicamente o próximo paciente livre da fila via Lua 4-Keys (RF-03).

        Registra presença idempotente do médico em plantao:medicos_ativos e executa
        varredura atômica multi-candidato eliminando corridas em cascata.
        Regras: RN01, RN02, RN05 e docs/explanation/domains/queue-domain.md
        """
        if self._alocacao_service is None:
            raise RuntimeError(
                "AlocacaoChamadaService não configurado para aquisição de "
                f"pacientes pelo médico '{command.medico_id}'."
            )

        await self._queue_engine.registrar_medico_ativo(command.medico_id)
        ttl = (
            command.ttl_segundos
            if command.ttl_segundos is not None
            else (await self._obter_politica_plantao()).tempo_tolerancia_ring_segundos
        )
        return await self._alocacao_service.alocar_proximo_paciente(
            medico_id=command.medico_id,
            ttl_segundos=ttl,
            max_scan=command.max_scan,
        )

    async def remover_da_fila(self, atendimento_id: UUID) -> bool:
        """Remove atendimento da fila virtual ZSET se presente (RN01).

        Regras: docs/explanation/domains/queue-domain.md
        """
        return await self._queue_engine.remover_da_fila(atendimento_id)

    async def obter_posicao_fila(self, atendimento_id: UUID) -> int | None:
        """Retorna posição 1-based do atendimento na fila ou None se ausente (RN01).

        Regras: docs/explanation/domains/queue-domain.md
        """
        rank, _ = await self._queue_engine.obter_posicao_e_tamanho(atendimento_id)
        return (rank + 1) if rank is not None else None

    async def obter_tamanho_fila(self) -> int:
        """Retorna o número total de pacientes aguardando na fila virtual (RN05).

        Regras: docs/explanation/domains/queue-domain.md
        """
        return await self._queue_engine.obter_tamanho_fila()

    async def admitir_atendimento_apto(
        self,
        atendimento_id: UUID,
        codigo_autorizacao: str | None = None,
    ) -> AdmissaoAptoResult:
        """Promove atendimento para APTO_PARA_CHAMADA pós-commit (RN03).

        Regras: docs/explanation/domains/queue-domain.md
        """
        atendimento = await self._db_session.get(Atendimento, atendimento_id)
        if atendimento is None:
            raise AtendimentoNaoEncontradoError(
                f"Atendimento '{atendimento_id}' não encontrado."
            )

        if (
            atendimento.status
            != StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value
        ):
            ts_base = atendimento.data_entrada_fila or atendimento.criado_em
            score = calcular_score(atendimento.prioridade_clinica, ts_base)
            return AdmissaoAptoResult(
                promovido=False, status=str(atendimento.status), score=score
            )

        estado_anterior = str(atendimento.status)
        atendimento.promover_para_apto()
        if self._audit_trail is not None:
            payload: dict[str, object] = {"canal": "ARQ_WORKER"}
            if codigo_autorizacao is not None:
                payload["codigo_autorizacao"] = codigo_autorizacao
            await self._audit_trail.record_event(
                atendimento_id=atendimento_id,
                ator_tipo=AtorTipo.SISTEMA,
                ator_papel=AtorPapel.WORKER_ARQ,
                tipo_evento="ELEGIBILIDADE_CONFIRMADA",
                ator_id=None,
                estado_anterior=estado_anterior,
                novo_estado=str(atendimento.status),
                tcle_hash=_safe_tcle_hash(atendimento),
                payload=payload,
            )

        ts_base = atendimento.data_entrada_fila or atendimento.criado_em
        score = calcular_score(atendimento.prioridade_clinica, ts_base)
        await self._db_session.commit()

        await self._queue_engine.inserir_ou_atualizar_fila(atendimento_id, score)
        logger.info(
            "Attendance %s promoted to APTO and ingested into queue with score=%d",
            atendimento_id,
            score,
        )
        return AdmissaoAptoResult(promovido=True, status="aprovado", score=score)

    async def resolver_ring_timeout(
        self,
        atendimento_id: UUID,
        medico_id: UUID,
        notifier: PacienteAusenteNotifierPort | None = None,
    ) -> str:
        """Resolve deterministicamente timeout de toque de 45s (RN02, ADR-002).

        Regras: docs/explanation/domains/queue-domain.md
        Decisões: docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md
        """
        atendimento = await self._db_session.get(
            Atendimento, atendimento_id, with_for_update=True
        )
        if atendimento is None:
            logger.warning(
                "Ring timeout task: attendance %s not found",
                atendimento_id,
            )
            return "not_found"

        current_status = atendimento.status
        if current_status == StatusAtendimento.CHAMANDO_PACIENTE.value:
            return await self._aplicar_no_show_timeout(
                atendimento=atendimento,
                medico_id=medico_id,
                notifier=notifier,
            )

        if current_status == StatusAtendimento.EM_ATENDIMENTO.value:
            await self._queue_engine.promover_para_consulta(medico_id, atendimento_id)
            logger.info(
                "Call answered for attendance %s; promoted active lock",
                atendimento_id,
            )
            return "active_consultation_preserved"

        await self._queue_engine.liberar_ring(medico_id, atendimento_id)
        return "already_finalized"

    async def _aplicar_no_show_timeout(
        self,
        *,
        atendimento: Atendimento,
        medico_id: UUID,
        notifier: PacienteAusenteNotifierPort | None,
    ) -> str:
        atendimento_id = atendimento.id
        paciente_id = atendimento.paciente_id
        estado_anterior = str(atendimento.status)
        atendimento.registrar_ausencia_paciente()

        if self._audit_trail is not None:
            await self._audit_trail.record_event(
                atendimento_id=atendimento_id,
                ator_tipo=AtorTipo.SISTEMA,
                ator_papel=AtorPapel.WORKER_ARQ,
                tipo_evento="TIMEOUT_CHAMADA_NO_SHOW",
                ator_id=None,
                estado_anterior=estado_anterior,
                novo_estado=str(atendimento.status),
                tcle_hash=_safe_tcle_hash(atendimento),
                payload={"medico_id": str(medico_id), "tempo_toque_segundos": 45},
            )
        await self._db_session.commit()

        await self._queue_engine.liberar_ring(medico_id, atendimento_id)
        dispatch_notifier = notifier or LoggingPacienteAusenteNotifier()
        await dispatch_notifier.emitir_paciente_ausente(
            PacienteAusenteEvent(
                atendimento_id=atendimento_id,
                medico_id=medico_id,
                paciente_id=paciente_id,
                tempo_toque_segundos=45,
            )
        )
        logger.info(
            "Patient absent (no-show) recorded for attendance %s (medico=%s)",
            atendimento_id,
            medico_id,
        )
        return "no_show_recorded"

    async def atender_chamada(
        self,
        atendimento_id: UUID,
    ) -> None:
        """Transiciona para EM_ATENDIMENTO e promove lock ativo pós-commit (RN02, RN03).

        Idempotente quando já se encontra em EM_ATENDIMENTO.
        Regras: docs/explanation/domains/queue-domain.md
        """
        atendimento = await self._db_session.get(
            Atendimento, atendimento_id, with_for_update=True
        )
        if atendimento is None:
            raise AtendimentoNaoEncontradoError(
                f"Atendimento '{atendimento_id}' não encontrado."
            )

        if atendimento.status == StatusAtendimento.EM_ATENDIMENTO.value:
            if atendimento.medico_id is not None:
                await self._queue_engine.promover_para_consulta(
                    atendimento.medico_id, atendimento.id
                )
            return

        if atendimento.status != StatusAtendimento.CHAMANDO_PACIENTE.value:
            raise TransicaoEstadoInvalidaError(
                f"Apenas atendimentos em '{StatusAtendimento.CHAMANDO_PACIENTE}' "
                f"podem ser atendidos. Estado atual: '{atendimento.status}'."
            )

        estado_anterior = str(atendimento.status)
        medico_id = atendimento.medico_id
        atendimento.atender_chamada()
        if self._audit_trail is not None:
            await self._audit_trail.record_event(
                atendimento_id=atendimento.id,
                ator_tipo=AtorTipo.PACIENTE,
                ator_papel=AtorPapel.PACIENTE,
                tipo_evento="CHAMADA_ATENDIDA",
                ator_id=atendimento.paciente_id,
                estado_anterior=estado_anterior,
                novo_estado=str(atendimento.status),
                tcle_hash=_safe_tcle_hash(atendimento),
                payload={"medico_id": str(medico_id)} if medico_id else {},
            )
        await self._db_session.commit()

        if medico_id is not None:
            await self._queue_engine.promover_para_consulta(medico_id, atendimento_id)

    async def concluir_atendimento(
        self,
        atendimento_id: UUID,
        *,
        auto_commit: bool = True,
    ) -> UUID | None:
        """Transiciona atendimento em EM_ATENDIMENTO para CONCLUIDO (RN03).

        Com ``auto_commit=False``, executa apenas flush para participação em transação
        única externa e delega a liberação de ``lock:consulta_ativa:medico:{id}`` ao
        chamador após o commit final.
        Regras: docs/explanation/domains/queue-domain.md
        """
        atendimento = await self._db_session.get(
            Atendimento, atendimento_id, with_for_update=True
        )
        if atendimento is None:
            raise AtendimentoNaoEncontradoError(
                f"Atendimento '{atendimento_id}' não encontrado."
            )

        medico_id = atendimento.medico_id
        if atendimento.status != StatusAtendimento.CONCLUIDO.value:
            atendimento.concluir_atendimento()
            if auto_commit:
                await self._db_session.commit()
            else:
                await self._db_session.flush()

        if auto_commit and medico_id is not None:
            await self._queue_engine.liberar_consulta(medico_id)
        return medico_id

    async def liberar_consulta_ativa_medico(self, medico_id: UUID) -> None:
        """Libera lock de consulta ativa do médico após commit externo (RN02, ADR-001).

        Regras: docs/explanation/domains/queue-domain.md
        """
        await self._queue_engine.liberar_consulta(medico_id)

    async def _buscar_lote_orfaos(
        self,
        *,
        cutoff_em: datetime,
        cursor_criado_em: datetime | None,
        cursor_id: UUID | None,
        batch_size: int,
    ) -> list[Atendimento]:
        stmt = select(Atendimento).where(
            Atendimento.status == StatusAtendimento.APTO_PARA_CHAMADA.value,
            Atendimento.atualizado_em <= cutoff_em,
        )
        if cursor_criado_em is not None and cursor_id is not None:
            stmt = stmt.where(
                or_(
                    Atendimento.criado_em > cursor_criado_em,
                    and_(
                        Atendimento.criado_em == cursor_criado_em,
                        Atendimento.id > cursor_id,
                    ),
                )
            )
        stmt = stmt.order_by(Atendimento.criado_em.asc(), Atendimento.id.asc()).limit(
            batch_size
        )
        res = await self._db_session.execute(stmt)
        return list(res.scalars().all())

    async def _reconciliar_item_orfao(self, atend: Atendimento) -> str | None:
        if await self._queue_engine.esta_bloqueado_para_reconciliacao(
            atend.id, atend.medico_id
        ):
            return None

        stmt_status = select(Atendimento.status).where(Atendimento.id == atend.id)
        status_atual = (
            await self._db_session.execute(stmt_status)
        ).scalar_one_or_none()
        if status_atual != StatusAtendimento.APTO_PARA_CHAMADA.value:
            return None

        ts_base = atend.data_entrada_fila or atend.criado_em
        score = calcular_score(atend.prioridade_clinica, ts_base)
        await self._queue_engine.inserir_ou_atualizar_fila(atend.id, score, nx=True)
        logger.warning(
            "Sweeper restored orphan attendance %s into queue with score=%d",
            atend.id,
            score,
        )
        return str(atend.id)

    async def _reconciliar_lote_orfaos(self, batch: list[Atendimento]) -> list[str]:
        reconciled_ids: list[str] = []
        for atend in batch:
            reconciled_id = await self._reconciliar_item_orfao(atend)
            if reconciled_id is not None:
                reconciled_ids.append(reconciled_id)
        return reconciled_ids

    async def reconciliar_fila_orfaos(
        self,
        cutoff_em: datetime,
        batch_size: int = 200,
    ) -> tuple[int, list[str]]:
        """Reinsere atendimentos APTO ausentes no ZSET em lotes keyset (RN01, RN02).

        Regras: docs/explanation/domains/queue-domain.md
        ADR: docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md
        """
        total_scanned = 0
        reconciled_ids: list[str] = []
        cursor_criado_em: datetime | None = None
        cursor_id: UUID | None = None

        while True:
            batch = await self._buscar_lote_orfaos(
                cutoff_em=cutoff_em,
                cursor_criado_em=cursor_criado_em,
                cursor_id=cursor_id,
                batch_size=batch_size,
            )
            if not batch:
                break

            total_scanned += len(batch)
            cursor_criado_em = batch[-1].criado_em
            cursor_id = batch[-1].id
            reconciled_ids.extend(await self._reconciliar_lote_orfaos(batch))

        return total_scanned, reconciled_ids

    async def buscar_atendimento(
        self,
        atendimento_id: UUID,
    ) -> AtendimentoSnapshotDTO | None:
        """Retorna snapshot imutável do atendimento por ID sem vazar ORM (ADR-001).

        Regras: docs/explanation/domains/queue-domain.md
        """
        stmt = select(Atendimento).where(Atendimento.id == atendimento_id)
        res = await self._db_session.execute(stmt)
        atend = res.scalar_one_or_none()
        if atend is None:
            return None
        return AtendimentoSnapshotDTO(
            id=atend.id,
            paciente_id=atend.paciente_id,
            medico_id=atend.medico_id,
            status=atend.status,
            prioridade_clinica=int(atend.prioridade_clinica),
            tcle_hash=atend.tcle_hash,
            data_entrada_fila=atend.data_entrada_fila,
            criado_em=atend.criado_em,
            is_terminal=atend.status in TERMINAL_STATUSES,
            chamada_iniciada_em=atend.chamada_iniciada_em,
        )

    async def listar_historico_paciente(
        self,
        paciente_id: UUID,
    ) -> list[AtendimentoHistoricoQueueDTO]:
        """Lista histórico de atendimentos do paciente via ORM e TriagePort (RF-07).

        Regras: docs/explanation/domains/queue-domain.md
        """
        stmt = (
            select(Atendimento)
            .where(Atendimento.paciente_id == paciente_id)
            .order_by(Atendimento.criado_em.desc(), Atendimento.id.desc())
        )
        res = await self._db_session.execute(stmt)
        atendimentos = [
            atend for atend in res.scalars().all() if atend.paciente_id == paciente_id
        ]
        if not atendimentos:
            return []

        queixas: dict[UUID, str | None] = {}
        if self._triage_port is not None:
            queixas = await self._triage_port.obter_queixas_por_atendimentos(
                atendimento_ids=[atend.id for atend in atendimentos],
            )

        return [
            AtendimentoHistoricoQueueDTO(
                atendimento_id=atend.id,
                paciente_id=atend.paciente_id,
                status=str(atend.status).strip().upper(),
                prioridade_clinica=int(atend.prioridade_clinica),
                criado_em=atend.criado_em,
                finalizado_em=atend.chamada_finalizada_em,
                medico_id=atend.medico_id,
                queixa_principal=queixas.get(atend.id),
            )
            for atend in atendimentos
        ]

    async def obter_posicao_e_estimativa(
        self,
        atendimento_id: UUID,
    ) -> PosicaoFilaResult:
        """Retorna posição ordinal, timer e estimativa usando TMA da política (RN01).

        Regras: docs/explanation/domains/queue-domain.md
        """
        atendimento = await self._db_session.get(Atendimento, atendimento_id)
        if atendimento is None:
            raise AtendimentoNaoEncontradoError(
                f"Atendimento '{atendimento_id}' não encontrado."
            )

        rank, total_aguardando = await self._queue_engine.obter_posicao_e_tamanho(
            atendimento_id
        )
        status_atual = str(atendimento.status)
        prioridade = int(atendimento.prioridade_clinica)
        chamada_em = atendimento.chamada_iniciada_em

        if atendimento.is_finalizado:
            return PosicaoFilaResult(
                atendimento_id=atendimento_id,
                status=status_atual,
                posicao=None,
                total_aguardando=total_aguardando,
                tempo_estimado_segundos=None,
                prioridade_clinica=prioridade,
                chamada_iniciada_em=chamada_em,
                ttl_segundos=None,
            )

        policy = await self._obter_politica_plantao()
        if status_atual in (
            StatusAtendimento.CHAMANDO_PACIENTE.value,
            StatusAtendimento.EM_ATENDIMENTO.value,
        ):
            ttl = (
                policy.tempo_tolerancia_ring_segundos
                if status_atual == StatusAtendimento.CHAMANDO_PACIENTE.value
                else None
            )
            return PosicaoFilaResult(
                atendimento_id=atendimento_id,
                status=status_atual,
                posicao=0,
                total_aguardando=total_aguardando,
                tempo_estimado_segundos=0,
                prioridade_clinica=prioridade,
                chamada_iniciada_em=chamada_em,
                ttl_segundos=ttl,
            )

        posicao = (rank + 1) if rank is not None else None
        medicos_ativos = await self._queue_engine.obter_medicos_ativos_count()
        medicos_div = max(medicos_ativos, 1)

        tempo_estimado: int | None = None
        if posicao is not None:
            tempo_estimado = int((posicao * policy.tma_padrao_segundos) / medicos_div)

        return PosicaoFilaResult(
            atendimento_id=atendimento_id,
            status=status_atual,
            posicao=posicao,
            total_aguardando=total_aguardando,
            tempo_estimado_segundos=tempo_estimado,
            prioridade_clinica=prioridade,
            chamada_iniciada_em=None,
            ttl_segundos=None,
        )

    async def cancelar_atendimento_paciente(
        self,
        atendimento_id: UUID,
        motivo: str | None = None,
    ) -> CancelarAtendimentoResult:
        """Cancela atendimento voluntariamente e limpa Valkey somente pós-commit (RN06).

        Se o cancelamento ocorrer durante CHAMANDO_PACIENTE (recusa ativa ao toque),
        publica CALL_CANCELLED no canal do médico para desbloqueio imediato da estação.
        Regras: docs/explanation/domains/queue-domain.md
        """
        atendimento = await self._db_session.get(
            Atendimento, atendimento_id, with_for_update=True
        )
        if atendimento is None:
            raise AtendimentoNaoEncontradoError(
                f"Atendimento '{atendimento_id}' não encontrado."
            )

        estado_anterior = str(atendimento.status)
        medico_id_anterior = atendimento.medico_id
        motivo_registrado = atendimento.cancelar_pelo_paciente(motivo)
        novo_status = str(atendimento.status)
        cancelado_em = (
            atendimento.chamada_finalizada_em
            or atendimento.atualizado_em
            or datetime.now(UTC)
        )

        if self._audit_trail is not None:
            await self._audit_trail.record_event(
                atendimento_id=atendimento_id,
                ator_tipo=AtorTipo.PACIENTE,
                ator_papel=AtorPapel.PACIENTE,
                tipo_evento="ATENDIMENTO_CANCELADO_PACIENTE",
                ator_id=atendimento.paciente_id,
                estado_anterior=estado_anterior,
                novo_estado=novo_status,
                tcle_hash=_safe_tcle_hash(atendimento),
                payload={"motivo": motivo_registrado} if motivo_registrado else {},
            )

        await self._db_session.commit()

        await self._queue_engine.remover_da_fila(atendimento_id)
        if medico_id_anterior is not None:
            await self._queue_engine.liberar_ring(medico_id_anterior, atendimento_id)
            if estado_anterior == StatusAtendimento.CHAMANDO_PACIENTE.value:
                await self._notificar_cancelamento_chamada_medico(
                    medico_id=medico_id_anterior,
                    atendimento_id=atendimento_id,
                    status_str=novo_status,
                    motivo=motivo_registrado,
                    cancelado_em=cancelado_em,
                )

        logger.info(
            "Attendance %s cancelled by patient (motivo=%s)",
            atendimento_id,
            motivo_registrado,
        )
        return CancelarAtendimentoResult(
            atendimento_id=atendimento_id,
            status=novo_status,
            cancelado_em=cancelado_em,
            motivo=motivo_registrado,
        )

    async def _notificar_cancelamento_chamada_medico(
        self,
        *,
        medico_id: UUID,
        atendimento_id: UUID,
        status_str: str,
        motivo: str | None,
        cancelado_em: datetime,
    ) -> None:
        try:
            await self._queue_engine.publicar_evento_medico(
                medico_id,
                {
                    "event": "CALL_CANCELLED",
                    "atendimento_id": str(atendimento_id),
                    "medico_id": str(medico_id),
                    "status": status_str,
                    "motivo": motivo,
                    "timestamp": cancelado_em.isoformat(),
                },
            )
        except Exception:
            logger.exception(
                "Failed to publish CALL_CANCELLED for attendance %s (medico=%s)",
                atendimento_id,
                medico_id,
            )

    async def processar_piora_clinica(
        self,
        command: PioraClinicaInput,
    ) -> PioraClinicaResult:
        """Reavalia risco clínico após comunicação de piora de sintomas (RF-06).

        Executa mutações Valkey estritamente após commit no banco e calcula score
        com a prioridade persistida no agregado.
        Regras: RN01, RN04 e docs/explanation/domains/queue-domain.md
        História: docs/user-stories/US-06-deterioracao-clinica-escape-samu.md
        """
        if self._triage_port is None:
            raise RuntimeError(
                "TriagePort não configurado no FilaService para "
                f"atendimento '{command.atendimento_id}'."
            )

        atendimento = await self._db_session.get(
            Atendimento, command.atendimento_id, with_for_update=True
        )
        if atendimento is None:
            raise AtendimentoNaoEncontradoError(
                f"Atendimento '{command.atendimento_id}' não encontrado."
            )

        if (
            atendimento.is_finalizado
            or atendimento.status == StatusAtendimento.EM_ATENDIMENTO.value
        ):
            raise TransicaoEstadoInvalidaError(
                "Não é possível acionar piora clínica para atendimento no "
                f"estado '{atendimento.status}'; esperados status válidos para "
                "piora: ['TRIADO_AGUARDANDO_ELEGIBILIDADE', 'APTO_PARA_CHAMADA', "
                "'CHAMANDO_PACIENTE']."
            )

        triage_eval = await self._triage_port.avaliar_risco(
            queixa_principal=command.queixa_adicional
            or "Piora de sintomas na fila virtual",
            sintomas=command.novos_sintomas,
            escala_dor=command.escala_dor,
            tcle_hash=_safe_tcle_hash(atendimento),
            raise_on_emergency=False,
            atendimento_id=atendimento.id,
        )

        if triage_eval.alerta_samu_disparado or triage_eval.prioridade_clinica == 1:
            return await self._processar_piora_emergencia_samu(
                atendimento=atendimento,
                triage_eval=triage_eval,
            )

        return await self._processar_piora_recalculo(
            atendimento=atendimento,
            nova_prioridade=triage_eval.prioridade_clinica,
        )

    async def _processar_piora_emergencia_samu(
        self,
        *,
        atendimento: Atendimento,
        triage_eval: TriageEvaluationDTO,
    ) -> PioraClinicaResult:
        atendimento_id = atendimento.id
        estado_anterior = str(atendimento.status)
        medico_id_anterior = atendimento.medico_id
        paciente_id = atendimento.paciente_id

        atendimento.cancelar_pelo_paciente("ENCAMINHADO_SAMU_PIORA_CLINICA")
        status_final = str(atendimento.status)
        cancelado_em = atendimento.chamada_finalizada_em or datetime.now(UTC)

        if self._audit_trail is not None:
            await self._audit_trail.record_event(
                atendimento_id=atendimento_id,
                ator_tipo=AtorTipo.PACIENTE,
                ator_papel=AtorPapel.PACIENTE,
                tipo_evento="PIORA_CLINICA_REGISTRADA",
                ator_id=paciente_id,
                estado_anterior=estado_anterior,
                novo_estado=status_final,
                tcle_hash=_safe_tcle_hash(atendimento),
                payload={
                    "alerta_samu": True,
                    "motivo": "ENCAMINHADO_SAMU_PIORA_CLINICA",
                    "prioridade": 1,
                },
            )
        await self._db_session.commit()

        await self._queue_engine.remover_da_fila(atendimento_id)
        if medico_id_anterior is not None:
            await self._queue_engine.liberar_ring(medico_id_anterior, atendimento_id)
            if estado_anterior == StatusAtendimento.CHAMANDO_PACIENTE.value:
                await self._notificar_cancelamento_chamada_medico(
                    medico_id=medico_id_anterior,
                    atendimento_id=atendimento_id,
                    status_str=status_final,
                    motivo="ENCAMINHADO_SAMU_PIORA_CLINICA",
                    cancelado_em=cancelado_em,
                )

        instrucoes = triage_eval.instrucao_redirecionamento or _INSTRUCOES_SAMU_FALLBACK
        logger.warning(
            "Patient %s reported severe deterioration in attendance %s. "
            "Dispatched SAMU escape.",
            paciente_id,
            atendimento_id,
        )
        return PioraClinicaResult(
            atendimento_id=atendimento_id,
            prioridade_clinica=1,
            alerta_samu_disparado=True,
            redirecionado_emergencia=True,
            nova_posicao=None,
            instrucoes=instrucoes,
            status_atendimento=status_final,
        )

    async def _processar_piora_recalculo(
        self,
        *,
        atendimento: Atendimento,
        nova_prioridade: int,
    ) -> PioraClinicaResult:
        atendimento_id = atendimento.id
        if nova_prioridade < atendimento.prioridade_clinica:
            atendimento.atualizar_prioridade(nova_prioridade)

        prioridade_persistida = int(atendimento.prioridade_clinica)
        status_atual = str(atendimento.status)
        ts_base = atendimento.data_entrada_fila or atendimento.criado_em

        if self._audit_trail is not None:
            await self._audit_trail.record_event(
                atendimento_id=atendimento_id,
                ator_tipo=AtorTipo.PACIENTE,
                ator_papel=AtorPapel.PACIENTE,
                tipo_evento="PIORA_CLINICA_REGISTRADA",
                ator_id=atendimento.paciente_id,
                estado_anterior=status_atual,
                novo_estado=status_atual,
                tcle_hash=_safe_tcle_hash(atendimento),
                payload={"nova_prioridade": prioridade_persistida},
            )

        await self._db_session.commit()

        nova_pos: int | None = None
        if status_atual == StatusAtendimento.APTO_PARA_CHAMADA.value:
            score = calcular_score(prioridade_persistida, ts_base)
            rank = await self._queue_engine.inserir_ou_atualizar_fila(
                atendimento_id, score
            )
            nova_pos = (rank + 1) if rank is not None else None

        logger.info(
            "Attendance %s reclassified to priority %d (new position=%s)",
            atendimento_id,
            prioridade_persistida,
            nova_pos,
        )
        return PioraClinicaResult(
            atendimento_id=atendimento_id,
            prioridade_clinica=prioridade_persistida,
            alerta_samu_disparado=False,
            redirecionado_emergencia=False,
            nova_posicao=nova_pos,
            instrucoes="Prioridade recalculada com sucesso na fila de espera.",
            status_atendimento=status_atual,
        )

    async def regularizar_atendimento(
        self, cmd: RegularizacaoFilaCommand
    ) -> RegularizacaoFilaResult:
        """Regulariza atendimento retido por elegibilidade ou contingência assistencial.

        Regras: RN01, RN03, RF-05 e docs/explanation/domains/queue-domain.md
        História: docs/user-stories/US-05-regularizacao-elegibilidade-fila.md
        """
        motivo_limpo = cmd.motivo.strip() if cmd.motivo else ""
        if len(motivo_limpo) < 3:
            raise ValidationError(
                f"Motivo da regularização '{cmd.motivo}' inválido; "
                "esperado texto com no mínimo 3 caracteres."
            )

        atendimento = await self._db_session.get(Atendimento, cmd.atendimento_id)
        if atendimento is None:
            raise AtendimentoNaoEncontradoError(
                f"Atendimento '{cmd.atendimento_id}' não encontrado."
            )

        if atendimento.is_finalizado or atendimento.status not in (
            StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value,
            StatusAtendimento.APTO_PARA_CHAMADA.value,
        ):
            permitidos = (
                f"['{StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value}', "
                f"'{StatusAtendimento.APTO_PARA_CHAMADA.value}']"
            )
            raise TransicaoEstadoInvalidaError(
                f"Não é possível regularizar atendimento no status "
                f"'{atendimento.status}'; esperados: {permitidos}."
            )

        ts_base = atendimento.data_entrada_fila or atendimento.criado_em
        score = calcular_score(atendimento.prioridade_clinica, ts_base)

        if atendimento.status == StatusAtendimento.APTO_PARA_CHAMADA.value:
            return RegularizacaoFilaResult(
                atendimento_id=atendimento.id,
                promovido=False,
                status="already_promoted",
                score=score,
                tipo_contingencia=cmd.tipo_contingencia,
                mensagem="Atendimento já está apto para chamada na fila virtual.",
            )

        estado_anterior = str(atendimento.status)
        atendimento.promover_para_apto()
        if self._audit_trail is not None:
            await self._audit_trail.record_event(
                atendimento_id=atendimento.id,
                ator_tipo=AtorTipo.SISTEMA,
                ator_papel=AtorPapel.SISTEMA,
                tipo_evento="ELEGIBILIDADE_CONFIRMADA",
                ator_id=None,
                estado_anterior=estado_anterior,
                novo_estado=str(atendimento.status),
                tcle_hash=_safe_tcle_hash(atendimento),
                payload={
                    "canal": "REGULARIZACAO_CONTINGENCIA",
                    "tipo_contingencia": cmd.tipo_contingencia,
                    "motivo": motivo_limpo,
                },
            )

        atendimento_id = atendimento.id
        ts_promovido = atendimento.data_entrada_fila or atendimento.criado_em
        score_promovido = calcular_score(atendimento.prioridade_clinica, ts_promovido)
        await self._db_session.commit()

        await self._queue_engine.inserir_ou_atualizar_fila(
            atendimento_id, score_promovido
        )

        logger.info(
            "Attendance %s regularized (contingency=%s) and promoted (score=%d)",
            atendimento_id,
            cmd.tipo_contingencia,
            score_promovido,
        )
        return RegularizacaoFilaResult(
            atendimento_id=atendimento_id,
            promovido=True,
            status=StatusAtendimento.APTO_PARA_CHAMADA.value,
            score=score_promovido,
            tipo_contingencia=cmd.tipo_contingencia,
            mensagem="Atendimento regularizado com sucesso e promovido para apto.",
        )
