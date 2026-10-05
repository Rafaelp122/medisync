"""Application service for atomic call allocation (ADR-002)."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from arq.connections import ArqRedis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.realtime import (
    channel_doctor_calls,
    channel_queue_patient,
    publish_realtime_event,
)
from src.modules.queue.application.dtos import (
    AlocacaoChamadaResult,
    AlocarChamadaCommand,
)
from src.modules.queue.application.ports.allocation_port import (
    AllocationPort,
    AlocacaoCodigo,
)
from src.modules.queue.application.ports.notification_port import NotificationPort
from src.modules.queue.domain.exceptions import (
    AtendimentoNaoDisponivelError,
    AtendimentoNaoEncontradoError,
    MedicoOcupadoError,
)
from src.modules.queue.domain.models import Atendimento

logger = logging.getLogger("medisync.queue.alocacao")


class AlocacaoChamadaService:
    """Coordinates atomic queue allocation via Valkey Lua script and DB persistence."""

    def __init__(
        self,
        valkey: Redis,
        db_session: AsyncSession,
        lua_manager: AllocationPort,
        arq_pool: ArqRedis | None = None,
        notification_adapter: NotificationPort | None = None,
    ) -> None:
        self._valkey = valkey
        self._db_session = db_session
        self._lua_manager = lua_manager
        self._arq_pool = arq_pool
        self._notification_adapter = notification_adapter

    async def alocar_chamada(
        self,
        command: AlocarChamadaCommand,
    ) -> AlocacaoChamadaResult:
        """Atomically match doctor with patient via Lua, setting 45s locks.

        Return codes from alocar_chamada.lua:
        - 1: Success -> dual locks created, patient popped from queue.
        - 0: Doctor busy -> raises MedicoOcupadoError (HTTP 409).
        - -1: Patient snatched or unavailable ->
          raises AtendimentoNaoDisponivelError (HTTP 409).
        """
        k_medico = f"lock:{command.organizacao_id}:medico:{command.medico_id}"
        k_atend = f"lock:{command.organizacao_id}:atendimento:{command.atendimento_id}"
        k_fila = f"fila:{command.organizacao_id}:aptos"

        # 1. Execute Lua script for sub-10ms atomic allocation in Valkey
        allocation_args: list[object] = [
            str(command.medico_id),
            str(command.atendimento_id),
            command.ttl_segundos,
        ]
        codigo = await self._lua_manager.alocar_chamada(
            client=self._valkey,
            keys=[k_medico, k_atend, k_fila],
            args=allocation_args,
        )

        if codigo == AlocacaoCodigo.MEDICO_OCUPADO:
            logger.warning(
                "Doctor %s is already locked with active call (org=%d)",
                command.medico_id,
                command.organizacao_id,
            )
            raise MedicoOcupadoError(
                f"Médico '{command.medico_id}' já possui uma chamada ou consulta ativa."
            )

        if codigo == AlocacaoCodigo.INDISPONIVEL:
            logger.info(
                "Patient %s is no longer available in queue (org=%d)",
                command.atendimento_id,
                command.organizacao_id,
            )
            raise AtendimentoNaoDisponivelError(
                f"Atendimento '{command.atendimento_id}' não está disponível na fila "
                "ou foi reservado simultaneamente por outro profissional."
            )

        # 2. Synchronize PostgreSQL persistence within the same application flow
        try:
            atendimento = await self._db_session.get(
                Atendimento, command.atendimento_id
            )
            if not atendimento:
                raise AtendimentoNaoEncontradoError(
                    f"Atendimento '{command.atendimento_id}' "
                    "não foi encontrado no banco."
                )

            atendimento.iniciar_chamada(command.medico_id)
            await self._db_session.commit()
            await self._db_session.refresh(atendimento)
        except Exception:
            # On any DB failure or state exception, rollback Valkey locks
            await self.liberar_locks(
                command.organizacao_id,
                command.medico_id,
                command.atendimento_id,
            )
            raise

        # 3. Schedule deterministic 45s ring timeout in background worker (RN02)
        if self._arq_pool is not None:
            await self._arq_pool.enqueue_job(
                "resolver_ring_timeout_task",
                organizacao_id=command.organizacao_id,
                atendimento_id=str(command.atendimento_id),
                medico_id=str(command.medico_id),
                _defer_by=timedelta(seconds=command.ttl_segundos),
                _job_id=f"ring_timeout:{command.atendimento_id}",
            )

        # 4. Dispatch call notification to patient (WhatsApp/SMS)
        # Message failures MUST NOT block transactional queue progression
        if self._notification_adapter is not None and command.telefone_paciente:
            try:
                await self._notification_adapter.send_whatsapp(
                    to=command.telefone_paciente,
                    template="chamada_consulta",
                    params={
                        "atendimento_id": str(atendimento.id),
                        "medico_id": str(command.medico_id),
                    },
                )
            except Exception:
                logger.exception(
                    "Failed to dispatch call notification for attendance %s (to=%s). "
                    "Queue progression continued unaffected.",
                    atendimento.id,
                    command.telefone_paciente,
                )

        # 5. Broadcast real-time WebSocket events via Valkey Pub/Sub
        # Trigger doctor incoming call modal and notify waiting patient
        try:
            chamada_ts = (
                atendimento.chamada_iniciada_em or datetime.now(UTC)
            ).isoformat()
            await publish_realtime_event(
                valkey=self._valkey,
                channel=channel_doctor_calls(command.medico_id),
                payload={
                    "event": "INCOMING_CALL",
                    "atendimento_id": str(atendimento.id),
                    "medico_id": str(command.medico_id),
                    "ttl_segundos": command.ttl_segundos,
                    "chamada_iniciada_em": chamada_ts,
                },
            )
            await publish_realtime_event(
                valkey=self._valkey,
                channel=channel_queue_patient(command.atendimento_id),
                payload={
                    "event": "CALLED",
                    "atendimento_id": str(atendimento.id),
                    "medico_id": str(command.medico_id),
                    "status": atendimento.status,
                    "ttl_segundos": command.ttl_segundos,
                    "chamada_iniciada_em": chamada_ts,
                },
            )
        except Exception:
            logger.exception(
                "Failed to broadcast realtime call events for attendance %s. "
                "Queue progression continued unaffected.",
                atendimento.id,
            )

        logger.info(
            "Call allocated successfully: medico=%s, atendimento=%s (org=%d)",
            command.medico_id,
            command.atendimento_id,
            command.organizacao_id,
        )

        return AlocacaoChamadaResult(
            atendimento_id=atendimento.id,
            medico_id=command.medico_id,
            status=atendimento.status,
            chamada_iniciada_em=atendimento.chamada_iniciada_em or datetime.now(UTC),
            ttl_segundos=command.ttl_segundos,
        )

    async def liberar_locks(
        self,
        organizacao_id: int,
        medico_id: UUID,
        atendimento_id: UUID,
    ) -> None:
        """Release both doctor and attendance ring locks from Valkey."""
        k_medico = f"lock:{organizacao_id}:medico:{medico_id}"
        k_atend = f"lock:{organizacao_id}:atendimento:{atendimento_id}"
        await self._valkey.delete(k_medico, k_atend)

    async def verificar_lock_medico(
        self,
        organizacao_id: int,
        medico_id: UUID,
    ) -> bool:
        """Check whether doctor currently holds an active lock."""
        k_medico = f"lock:{organizacao_id}:medico:{medico_id}"
        exists = await self._valkey.exists(k_medico)  # pyright: ignore[reportUnknownMemberType]
        return bool(exists)

    async def verificar_lock_atendimento(
        self,
        organizacao_id: int,
        atendimento_id: UUID,
    ) -> bool:
        """Check whether attendance currently holds an active ring lock."""
        k_atend = f"lock:{organizacao_id}:atendimento:{atendimento_id}"
        exists = await self._valkey.exists(k_atend)  # pyright: ignore[reportUnknownMemberType]
        return bool(exists)

    async def obter_lock_medico_atendimento_id(
        self,
        organizacao_id: int,
        medico_id: UUID,
    ) -> str | None:
        """Retrieve attendance ID associated with doctor's active lock, if any."""
        k_medico = f"lock:{organizacao_id}:medico:{medico_id}"
        val = await self._valkey.get(k_medico)
        return str(val) if val else None
