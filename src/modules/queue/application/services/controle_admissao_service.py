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

FILA_APTOS_KEY = "fila:aptos"
PLANTAO_MEDICOS_KEY = "plantao:medicos_ativos"

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
    """Evaluates platform capacity using stochastic backpressure formula (RN05).

    Formula:
        (Pacientes Aguardando * TMA * alpha) / Médicos Ativos > Tempo Restante

    Regras: docs/explanation/domains/queue-domain.md
    """
    if alpha <= 0:
        raise ValidationError(
            f"Fator de segurança alpha '{alpha}' inválido; "
            "esperado valor positivo (> 0)."
        )
    if tma_estimado_segundos <= 0:
        raise ValidationError(
            f"TMA estimado '{tma_estimado_segundos}' inválido; "
            "esperado valor positivo (> 0)."
        )

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
    """Coordinates capacity evaluation, active doctor presence, and overflow events.

    Regras: RN05, docs/explanation/domains/queue-domain.md
    """

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
        """Avalia admissão estocástica e notifica transbordo se excedida (RN05).

        Regras: docs/explanation/domains/queue-domain.md
        """
        if command.pacientes_aguardando is None:
            card = await self._valkey.zcard(FILA_APTOS_KEY)  # pyright: ignore[reportUnknownMemberType]
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

    async def registrar_medico_ativo(self, medico_id: UUID) -> None:
        """Adiciona médico ao plantão ativo no Valkey (RN05).

        Regras: docs/explanation/domains/queue-domain.md
        """
        await self._valkey.sadd(PLANTAO_MEDICOS_KEY, str(medico_id))  # pyright: ignore[reportGeneralTypeIssues, reportUnknownMemberType]

    async def desregistrar_medico_ativo(self, medico_id: UUID) -> None:
        """Remove médico do plantão ativo no Valkey (RN05).

        Regras: docs/explanation/domains/queue-domain.md
        """
        await self._valkey.srem(PLANTAO_MEDICOS_KEY, str(medico_id))  # pyright: ignore[reportGeneralTypeIssues, reportUnknownMemberType]

    async def obter_medicos_ativos_count(self) -> int:
        """Retorna total de médicos ativos no plantão na plataforma (RN05).

        Regras: docs/explanation/domains/queue-domain.md
        """
        count = await self._valkey.scard(PLANTAO_MEDICOS_KEY)  # pyright: ignore[reportGeneralTypeIssues, reportUnknownMemberType, reportUnknownVariableType]
        return int(count)  # pyright: ignore[reportUnknownArgumentType]

    async def incrementar_admissoes_hoje(self) -> int:
        """Incrementa e retorna o contador diário de admissões no Valkey (RN05).

        Regras: docs/explanation/domains/queue-domain.md
        """
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        k = f"queue:admissoes:{today}"
        val = await self._valkey.incr(k)  # pyright: ignore[reportUnknownMemberType]
        await self._valkey.expire(k, 86400 * 2)  # pyright: ignore[reportUnknownMemberType]
        return int(val)

    async def obter_admissoes_hoje(self) -> int:
        """Retorna o total de admissões realizadas hoje no Valkey (RN05).

        Regras: docs/explanation/domains/queue-domain.md
        """
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        k = f"queue:admissoes:{today}"
        val = await self._valkey.get(k)  # pyright: ignore[reportUnknownMemberType]
        return int(val) if val is not None else 0
