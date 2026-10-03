"""Deterministic 45-second ring timeout task for no-show resolution (RN02)."""

import logging
from typing import Any
from uuid import UUID

from src.core.context import tenant_context
from src.modules.queue.application.ports import (
    LoggingPacienteAusenteNotifier,
    PacienteAusenteEvent,
    PacienteAusenteNotifierPort,
)
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.worker.context import get_db_session_from_ctx, get_valkey_from_ctx
from src.worker.tasks.base import monitored_task

logger = logging.getLogger("medisync.worker.ring_timeout")


@monitored_task
async def resolver_ring_timeout_task(
    ctx: dict[str, Any],
    organizacao_id: int,
    atendimento_id: str,
    medico_id: str,
    notifier: PacienteAusenteNotifierPort | None = None,
) -> dict[str, Any]:
    """Inspects attendance ring state after 45s; marks no-show if unanswered.

    If status is still CHAMANDO_PACIENTE:
      - Marks patient absent via atendimento.registrar_ausencia_paciente()
      - Commits the state change to PostgreSQL
      - Atomically deletes lock:{org}:medico:{medico_id} and lock:{org}:atendimento:...
      - Emits PacienteAusenteEvent
      - Returns {"status": "resolved", "action": "no_show_recorded"}

    If status is EM_ATENDIMENTO:
      - Patient answered in time and call connected
      - Clears ring lock and promotes doctor lock to consulta_ativa (TTL 7200s)
      - Returns {"status": "resolved", "action": "active_consultation_preserved"}

    If status is already finalized or cancelled:
      - Cleans up any lingering ring locks
      - Returns {"status": "resolved", "action": "already_finalized"}
    """
    dispatch_notifier = notifier or LoggingPacienteAusenteNotifier()
    valkey = get_valkey_from_ctx(ctx)

    k_medico_ring = f"lock:{organizacao_id}:medico:{medico_id}"
    k_atend_ring = f"lock:{organizacao_id}:atendimento:{atendimento_id}"
    k_medico_consulta = f"lock:{organizacao_id}:consulta_ativa:medico:{medico_id}"

    with tenant_context(organizacao_id):
        async with get_db_session_from_ctx(ctx) as session:
            atend_uuid = UUID(atendimento_id)
            atendimento = await session.get(Atendimento, atend_uuid)

            if not atendimento:
                logger.warning(
                    "Ring timeout task: attendance %s not found in org=%d",
                    atendimento_id,
                    organizacao_id,
                )
                return {"status": "not_found", "action": "ignored"}

            current_status = atendimento.status

            if current_status == StatusAtendimento.CHAMANDO_PACIENTE.value:
                # Patient did not answer within 45 seconds -> No-show
                atendimento.registrar_ausencia_paciente()
                await session.commit()

                # Atomically release ring locks from Valkey
                async with valkey.pipeline(transaction=True) as pipe:
                    pipe.delete(k_medico_ring)
                    pipe.delete(k_atend_ring)
                    await pipe.execute()

                event = PacienteAusenteEvent(
                    atendimento_id=atendimento.id,
                    organizacao_id=organizacao_id,
                    medico_id=UUID(medico_id),
                    paciente_id=atendimento.paciente_id,
                    tempo_toque_segundos=45,
                )
                await dispatch_notifier.emitir_paciente_ausente(event)

                logger.info(
                    "Patient absent (no-show) recorded for attendance %s (medico=%s)",
                    atendimento_id,
                    medico_id,
                )
                return {
                    "status": "resolved",
                    "action": "no_show_recorded",
                    "atendimento_id": atendimento_id,
                }

            if current_status == StatusAtendimento.EM_ATENDIMENTO.value:
                # Patient answered call within 45s -> Video consultation active
                async with valkey.pipeline(transaction=True) as pipe:
                    pipe.delete(k_atend_ring)
                    pipe.delete(k_medico_ring)
                    # 2-hour contingency TTL for active consultation
                    pipe.set(k_medico_consulta, atendimento_id, ex=7200)
                    await pipe.execute()

                logger.info(
                    "Call answered for attendance %s; promoted active lock",
                    atendimento_id,
                )
                return {
                    "status": "resolved",
                    "action": "active_consultation_preserved",
                    "atendimento_id": atendimento_id,
                }

            # Any other terminal state (e.g. cancelled by patient) -> release ring locks
            async with valkey.pipeline(transaction=True) as pipe:
                pipe.delete(k_medico_ring)
                pipe.delete(k_atend_ring)
                await pipe.execute()

            return {
                "status": "resolved",
                "action": "already_finalized",
                "current_status": current_status,
                "atendimento_id": atendimento_id,
            }
