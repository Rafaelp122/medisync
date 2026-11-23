"""Application service for atomic call allocation (ADR-002)."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import AtorPapel, AtorTipo, AuditTrailPort
from src.modules.queue.application.dtos import (
    AlocacaoChamadaResult,
    AlocarChamadaCommand,
)
from src.modules.queue.application.ports.allocation_port import AlocacaoCodigo
from src.modules.queue.application.ports.notification_port import NotificationPort
from src.modules.queue.application.ports.queue_engine_port import QueueEnginePort
from src.modules.queue.domain.exceptions import (
    AtendimentoNaoDisponivelError,
    AtendimentoNaoEncontradoError,
    MedicoOcupadoError,
)
from src.modules.queue.domain.models import Atendimento, StatusAtendimento
from src.modules.queue.domain.scoring import calcular_score

logger = logging.getLogger("medisync.queue.alocacao")


class AlocacaoChamadaService:
    """Coordena alocação atômica médico-paciente via QueueEnginePort e DB.

    Garante score 64-bit (RN01), lock 4-Keys/45s (RN02) e compensação segura.
    Regras: docs/explanation/domains/queue-domain.md
    ADR: docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md
    História: docs/user-stories/US-07-alocacao-chamada-medica.md.
    """

    def __init__(
        self,
        queue_engine: QueueEnginePort,
        db_session: AsyncSession,
        arq_pool: ArqRedis | None = None,
        notification_adapter: NotificationPort | None = None,
        audit_trail: AuditTrailPort | None = None,
    ) -> None:
        self._queue_engine = queue_engine
        self._db_session = db_session
        self._arq_pool = arq_pool
        self._notification_adapter = notification_adapter
        self._audit_trail: AuditTrailPort | None = audit_trail

    async def alocar_chamada(
        self,
        command: AlocarChamadaCommand,
    ) -> AlocacaoChamadaResult:
        """Executa alocação atômica 4-Keys e sincroniza DB/ARQ (ADR-002, ADR-007).

        Decisões: docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md
        Regras: docs/explanation/domains/queue-domain.md
        """
        codigo = await self._queue_engine.alocar_atendimento(
            medico_id=command.medico_id,
            atendimento_id=command.atendimento_id,
            ttl_segundos=command.ttl_segundos,
        )
        if codigo == AlocacaoCodigo.MEDICO_OCUPADO:
            logger.warning(
                "Doctor %s is already locked with active ring or consultation",
                command.medico_id,
            )
            raise MedicoOcupadoError(
                f"Médico '{command.medico_id}' já possui uma chamada ou consulta ativa."
            )
        if codigo == AlocacaoCodigo.INDISPONIVEL:
            logger.info(
                "Patient %s is no longer available in queue",
                command.atendimento_id,
            )
            raise AtendimentoNaoDisponivelError(
                f"Atendimento '{command.atendimento_id}' não está disponível na fila "
                "ou foi reservado simultaneamente por outro profissional."
            )

        return await self._persistir_e_notificar_alocacao(
            medico_id=command.medico_id,
            atendimento_id=command.atendimento_id,
            ttl_segundos=command.ttl_segundos,
            telefone_paciente=command.telefone_paciente,
        )

    async def alocar_proximo_paciente(
        self,
        medico_id: UUID,
        ttl_segundos: int = 45,
        max_scan: int = 50,
    ) -> AlocacaoChamadaResult | None:
        """Seleciona e aloca atomicamente próximo paciente via Lua ZRANGE (ADR-002).

        Decisões: docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md
        História: docs/user-stories/US-07-alocacao-chamada-medica.md.
        """
        codigo, atendimento_id = await self._queue_engine.alocar_proximo(
            medico_id=medico_id,
            ttl_segundos=ttl_segundos,
            max_scan=max_scan,
        )
        if codigo == AlocacaoCodigo.MEDICO_OCUPADO:
            logger.warning(
                "Doctor %s is busy with ring or active consultation",
                medico_id,
            )
            raise MedicoOcupadoError(
                f"Médico '{medico_id}' já possui uma chamada ou consulta ativa."
            )
        if codigo == AlocacaoCodigo.INDISPONIVEL or atendimento_id is None:
            logger.info(
                "No eligible unlocked patient available in queue for doctor %s",
                medico_id,
            )
            return None

        return await self._persistir_e_notificar_alocacao(
            medico_id=medico_id,
            atendimento_id=atendimento_id,
            ttl_segundos=ttl_segundos,
            telefone_paciente=None,
        )

    async def _persistir_e_notificar_alocacao(
        self,
        *,
        medico_id: UUID,
        atendimento_id: UUID,
        ttl_segundos: int,
        telefone_paciente: str | None,
    ) -> AlocacaoChamadaResult:
        score_out: list[int] = []
        try:
            result = await self._transicionar_chamada_db(
                medico_id=medico_id,
                atendimento_id=atendimento_id,
                ttl_segundos=ttl_segundos,
                score_out=score_out,
            )
        except Exception:
            await self._compensar_erro_db(
                medico_id=medico_id,
                atendimento_id=atendimento_id,
                score_devolucao=score_out[0] if score_out else None,
            )
            raise

        await self._agendar_ring_timeout(
            atendimento_id=atendimento_id,
            medico_id=medico_id,
            ttl_segundos=ttl_segundos,
            score_devolucao=score_out[0] if score_out else None,
        )
        await self._notificar_chamada_whatsapp(
            telefone_paciente=telefone_paciente,
            atendimento_id=atendimento_id,
            medico_id=medico_id,
        )
        await self._publicar_eventos_chamada(
            atendimento_id=atendimento_id,
            medico_id=medico_id,
            status_str=result.status,
            ttl_segundos=ttl_segundos,
            chamada_ts=result.chamada_iniciada_em,
        )

        logger.info(
            "Call allocated successfully: medico=%s, atendimento=%s",
            medico_id,
            atendimento_id,
        )
        return result

    async def _transicionar_chamada_db(
        self,
        *,
        medico_id: UUID,
        atendimento_id: UUID,
        ttl_segundos: int,
        score_out: list[int],
    ) -> AlocacaoChamadaResult:
        atendimento = await self._db_session.get(
            Atendimento, atendimento_id, with_for_update=True
        )
        if atendimento is None:
            raise AtendimentoNaoEncontradoError(
                f"Atendimento '{atendimento_id}' não foi encontrado no banco."
            )

        if atendimento.status == StatusAtendimento.APTO_PARA_CHAMADA.value:
            ts_base = atendimento.data_entrada_fila or atendimento.criado_em
            score_out.append(calcular_score(atendimento.prioridade_clinica, ts_base))

        estado_anterior = str(atendimento.status)
        atendimento.iniciar_chamada(medico_id)
        if self._audit_trail is not None:
            await self._audit_trail.record_event(
                atendimento_id=atendimento_id,
                ator_tipo=AtorTipo.PROFISSIONAL,
                ator_papel=AtorPapel.MEDICO,
                tipo_evento="CHAMADA_INICIADA",
                ator_id=medico_id,
                estado_anterior=estado_anterior,
                novo_estado=str(atendimento.status),
                tcle_hash=atendimento.tcle_hash
                if isinstance(atendimento.tcle_hash, str)
                else None,
                payload={"ring_timeout_segundos": ttl_segundos},
            )

        chamada_ts = atendimento.chamada_iniciada_em or datetime.now(UTC)
        result = AlocacaoChamadaResult(
            atendimento_id=atendimento.id,
            medico_id=medico_id,
            status=str(atendimento.status),
            chamada_iniciada_em=chamada_ts,
            ttl_segundos=ttl_segundos,
            paciente_id=atendimento.paciente_id,
            prioridade_clinica=int(atendimento.prioridade_clinica),
        )
        await self._db_session.commit()
        return result

    async def _compensar_erro_db(
        self,
        *,
        medico_id: UUID,
        atendimento_id: UUID,
        score_devolucao: int | None,
    ) -> None:
        await self._db_session.rollback()
        if score_devolucao is not None:
            await self._queue_engine.devolver_para_fila(
                atendimento_id=atendimento_id,
                score=score_devolucao,
                medico_id=medico_id,
                nx=True,
            )
            return
        await self._queue_engine.liberar_ring(medico_id, atendimento_id)

    async def _agendar_ring_timeout(
        self,
        *,
        atendimento_id: UUID,
        medico_id: UUID,
        ttl_segundos: int,
        score_devolucao: int | None,
    ) -> None:
        if self._arq_pool is None:
            return
        try:
            await self._arq_pool.enqueue_job(
                "resolver_ring_timeout_task",
                atendimento_id=str(atendimento_id),
                medico_id=str(medico_id),
                _defer_by=timedelta(seconds=ttl_segundos),
                _job_id=f"ring_timeout:{atendimento_id}",
            )
        except Exception:
            logger.critical(
                "Failed to enqueue resolver_ring_timeout_task for attendance %s "
                "(medico=%s); reverting attendance state and returning to queue",
                atendimento_id,
                medico_id,
                exc_info=True,
            )
            await self._compensar_falha_agendamento(
                atendimento_id=atendimento_id,
                medico_id=medico_id,
                score_devolucao=score_devolucao,
            )
            raise

    async def _compensar_falha_agendamento(
        self,
        *,
        atendimento_id: UUID,
        medico_id: UUID,
        score_devolucao: int | None,
    ) -> None:
        try:
            atendimento = await self._db_session.get(
                Atendimento, atendimento_id, with_for_update=True
            )
            if (
                atendimento is not None
                and atendimento.status == StatusAtendimento.CHAMANDO_PACIENTE.value
            ):
                ts_base = atendimento.data_entrada_fila or atendimento.criado_em
                score_devolucao = calcular_score(
                    atendimento.prioridade_clinica, ts_base
                )
                atendimento.reverter_para_apto()
                await self._db_session.commit()
        except Exception:
            await self._db_session.rollback()
            logger.critical(
                "Failed to revert DB state after ARQ enqueue error for attendance %s",
                atendimento_id,
                exc_info=True,
            )

        if score_devolucao is not None:
            await self._queue_engine.devolver_para_fila(
                atendimento_id=atendimento_id,
                score=score_devolucao,
                medico_id=medico_id,
                nx=True,
            )
            return
        await self._queue_engine.liberar_ring(medico_id, atendimento_id)

    async def _notificar_chamada_whatsapp(
        self,
        *,
        telefone_paciente: str | None,
        atendimento_id: UUID,
        medico_id: UUID,
    ) -> None:
        if self._notification_adapter is None or not telefone_paciente:
            return
        try:
            await self._notification_adapter.send_whatsapp(
                to=telefone_paciente,
                template="chamada_consulta",
                params={
                    "atendimento_id": str(atendimento_id),
                    "medico_id": str(medico_id),
                },
            )
        except Exception:
            logger.exception(
                "Failed to dispatch WhatsApp notification for attendance %s (to=%s). "
                "Queue progression continued unaffected.",
                atendimento_id,
                telefone_paciente,
            )

    async def _publicar_eventos_chamada(
        self,
        *,
        atendimento_id: UUID,
        medico_id: UUID,
        status_str: str,
        ttl_segundos: int,
        chamada_ts: datetime,
    ) -> None:
        try:
            chamada_iso = chamada_ts.isoformat()
            await self._queue_engine.publicar_evento_medico(
                medico_id,
                {
                    "event": "INCOMING_CALL",
                    "atendimento_id": str(atendimento_id),
                    "medico_id": str(medico_id),
                    "ttl_segundos": ttl_segundos,
                    "chamada_iniciada_em": chamada_iso,
                },
            )
            await self._queue_engine.publicar_evento_fila(
                atendimento_id,
                {
                    "event": "CALLED",
                    "atendimento_id": str(atendimento_id),
                    "medico_id": str(medico_id),
                    "status": status_str,
                    "ttl_segundos": ttl_segundos,
                    "chamada_iniciada_em": chamada_iso,
                },
            )
        except Exception:
            logger.exception(
                "Failed to broadcast realtime call events for attendance %s. "
                "Queue progression continued unaffected.",
                atendimento_id,
            )
