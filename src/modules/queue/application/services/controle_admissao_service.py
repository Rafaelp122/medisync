"""Stochastic admission control and backpressure service (RN05, ADR-002)."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis

from src.core.errors import ValidationError
from src.modules.queue.application.dtos import (
    AvaliacaoAdmissaoResult,
    AvaliarAdmissaoCommand,
)
from src.modules.queue.application.ports.queue_overflow_notifier import (
    LoggingQueueOverflowNotifier,
    QueueOverflowEvent,
    QueueOverflowNotifierPort,
)

logger = logging.getLogger("medisync.queue.admissao")

MENSAGEM_SEM_MEDICOS = (
    "O acolhimento virtual está temporariamente suspenso no momento pois não há "
    "médicos plantonistas ativos no turno. Por favor, procure atendimento presencial "
    "ou tente novamente em instantes."
)

MENSAGEM_COTA_ATINGIDA = (
    "A cota diária de atendimentos da unidade foi atingida para o dia de hoje. "
    "Por favor, procure atendimento presencial ou tente novamente amanhã."
)

MENSAGEM_CAPACIDADE_EXCEDIDA = (
    "O acolhimento virtual está temporariamente suspenso no momento pois a capacidade "
    "do plantão atual foi atingida (previsão de atendimento excede o tempo de "
    "plantão restante). Por favor, procure uma unidade de atendimento presencial "
    "ou tente novamente no próximo turno."
)

MENSAGEM_ADMISSAO_PERMITIDA = "Admissão permitida na fila virtual."


def avaliar_capacidade_admissao(
    pacientes_aguardando: int,
    medicos_ativos: int,
    tempo_restante_segundos: float,
    tma_estimado_segundos: int = 600,
    alpha: float = 1.25,
    total_admissoes_hoje: int = 0,
    cota_diaria_maxima: int | None = 300,
) -> AvaliacaoAdmissaoResult:
    """Evaluates unit capacity using stochastic backpressure formula (RN05).

    Formula:
        (Pacientes Aguardando * TMA * alpha) / Médicos Ativos > Tempo Restante

    Admission is suspended if:
    1. Active doctors <= 0 (prevents division by zero and queue accumulation).
    2. Daily completed admissions >= Daily max quota (Condition A).
    3. Estimated workload exceeds remaining shift capacity (Condition B).
    """
    if alpha <= 0:
        raise ValidationError("Fator de segurança alpha deve ser positivo.")
    if tma_estimado_segundos <= 0:
        raise ValidationError("TMA estimado deve ser positivo.")

    # 1. Active doctors check
    if medicos_ativos <= 0:
        return AvaliacaoAdmissaoResult(
            admissao_permitida=False,
            motivo_bloqueio="SEM_MEDICOS_ATIVOS",
            carga_estimada_segundos=0.0,
            tempo_restante_segundos=tempo_restante_segundos,
            pacientes_aguardando=pacientes_aguardando,
            medicos_ativos=medicos_ativos,
            alpha_utilizado=alpha,
            mensagem_explicativa=MENSAGEM_SEM_MEDICOS,
        )

    # 2. Daily quota check (Condition A)
    if cota_diaria_maxima is not None and total_admissoes_hoje >= cota_diaria_maxima:
        return AvaliacaoAdmissaoResult(
            admissao_permitida=False,
            motivo_bloqueio="COTA_ATINGIDA",
            carga_estimada_segundos=0.0,
            tempo_restante_segundos=tempo_restante_segundos,
            pacientes_aguardando=pacientes_aguardando,
            medicos_ativos=medicos_ativos,
            alpha_utilizado=alpha,
            mensagem_explicativa=MENSAGEM_COTA_ATINGIDA,
        )

    # 3. Stochastic workload vs. remaining shift capacity (Condition B)
    carga_estimada = (
        pacientes_aguardando * tma_estimado_segundos * alpha
    ) / medicos_ativos

    if carga_estimada > tempo_restante_segundos:
        return AvaliacaoAdmissaoResult(
            admissao_permitida=False,
            motivo_bloqueio="CAPACIDADE_EXCEDIDA",
            carga_estimada_segundos=carga_estimada,
            tempo_restante_segundos=tempo_restante_segundos,
            pacientes_aguardando=pacientes_aguardando,
            medicos_ativos=medicos_ativos,
            alpha_utilizado=alpha,
            mensagem_explicativa=MENSAGEM_CAPACIDADE_EXCEDIDA,
        )

    return AvaliacaoAdmissaoResult(
        admissao_permitida=True,
        motivo_bloqueio=None,
        carga_estimada_segundos=carga_estimada,
        tempo_restante_segundos=tempo_restante_segundos,
        pacientes_aguardando=pacientes_aguardando,
        medicos_ativos=medicos_ativos,
        alpha_utilizado=alpha,
        mensagem_explicativa=MENSAGEM_ADMISSAO_PERMITIDA,
    )


class ControleAdmissaoService:
    """Coordinates capacity evaluation, active doctor presence, and overflow events."""

    def __init__(
        self,
        valkey: Redis,
        notifier: QueueOverflowNotifierPort | None = None,
    ) -> None:
        self._valkey = valkey
        self._notifier: QueueOverflowNotifierPort = (
            notifier or LoggingQueueOverflowNotifier()
        )

    async def avaliar_admissao(
        self,
        command: AvaliarAdmissaoCommand,
    ) -> AvaliacaoAdmissaoResult:
        """Evaluates admission and emits QUEUE_OVERFLOW_TRANSIT if breached."""
        if command.pacientes_aguardando is None:
            card = await self._valkey.zcard(f"fila:{command.organizacao_id}:aptos")  # pyright: ignore[reportUnknownMemberType]
            pacientes = int(card)
        else:
            pacientes = command.pacientes_aguardando

        resultado = avaliar_capacidade_admissao(
            pacientes_aguardando=pacientes,
            medicos_ativos=command.medicos_ativos,
            tempo_restante_segundos=command.tempo_restante_segundos,
            tma_estimado_segundos=command.tma_estimado_segundos,
            alpha=command.alpha_margem,
            total_admissoes_hoje=command.total_admissoes_hoje,
            cota_diaria_maxima=command.cota_diaria_maxima,
        )

        if not resultado.admissao_permitida and resultado.motivo_bloqueio is not None:
            event = QueueOverflowEvent(
                organizacao_id=command.organizacao_id,
                motivo=resultado.motivo_bloqueio,
                pacientes_aguardando=pacientes,
                medicos_ativos=command.medicos_ativos,
                tempo_restante_segundos=command.tempo_restante_segundos,
                carga_estimada_segundos=resultado.carga_estimada_segundos,
                alpha_utilizado=resultado.alpha_utilizado,
                mensagem_orientacao=resultado.mensagem_explicativa,
            )
            await self._notifier.emitir_transbordo(event)

        return resultado

    async def registrar_medico_ativo(
        self,
        organizacao_id: int,
        medico_id: UUID,
    ) -> None:
        """Adds doctor to the active shift roster in Valkey."""
        k = f"plantao:{organizacao_id}:medicos_ativos"
        await self._valkey.sadd(k, str(medico_id))  # pyright: ignore[reportGeneralTypeIssues, reportUnknownMemberType]

    async def desregistrar_medico_ativo(
        self,
        organizacao_id: int,
        medico_id: UUID,
    ) -> None:
        """Removes doctor from the active shift roster in Valkey."""
        k = f"plantao:{organizacao_id}:medicos_ativos"
        await self._valkey.srem(k, str(medico_id))  # pyright: ignore[reportGeneralTypeIssues, reportUnknownMemberType]

    async def obter_medicos_ativos_count(
        self,
        organizacao_id: int,
    ) -> int:
        """Returns the number of active doctors on shift for the organization."""
        k = f"plantao:{organizacao_id}:medicos_ativos"
        count = await self._valkey.scard(k)  # pyright: ignore[reportGeneralTypeIssues, reportUnknownMemberType, reportUnknownVariableType]
        return int(count)  # pyright: ignore[reportUnknownArgumentType]

    async def incrementar_admissoes_hoje(
        self,
        organizacao_id: int,
    ) -> int:
        """Increments and returns total admissions for today in Valkey."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        k = f"cota:{organizacao_id}:{today}"
        val = await self._valkey.incr(k)  # pyright: ignore[reportUnknownMemberType]
        await self._valkey.expire(k, 86400 * 2)  # pyright: ignore[reportUnknownMemberType]
        return int(val)

    async def obter_admissoes_hoje(
        self,
        organizacao_id: int,
    ) -> int:
        """Returns total admissions for today from Valkey."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        k = f"cota:{organizacao_id}:{today}"
        val = await self._valkey.get(k)  # pyright: ignore[reportUnknownMemberType]
        return int(val) if val is not None else 0
