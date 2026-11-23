"""Stochastic admission control and backpressure service (RN05, ADR-002)."""

import logging
from uuid import UUID

from src.core.errors import ValidationError
from src.modules.queue.application.dtos import (
    AvaliacaoAdmissaoResult,
    AvaliarAdmissaoCommand,
)
from src.modules.queue.application.ports.queue_engine_port import QueueEnginePort

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
    """Coordinates capacity evaluation and active doctor presence via QueueEnginePort.

    Regras: RN05, docs/explanation/domains/queue-domain.md
    """

    def __init__(self, queue_engine: QueueEnginePort) -> None:
        self._queue_engine = queue_engine

    async def avaliar_admissao(
        self,
        command: AvaliarAdmissaoCommand,
    ) -> AvaliacaoAdmissaoResult:
        """Avalia admissão estocástica e loga transbordo quando bloqueada (RN05).

        Regras: docs/explanation/domains/queue-domain.md
        """
        pacientes = (
            await self._queue_engine.obter_tamanho_fila()
            if command.pacientes_aguardando is None
            else command.pacientes_aguardando
        )

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
            logger.warning(
                "Queue overflow/admission blocked (%s): awaiting=%d, "
                "active_doctors=%d, workload=%.1fs, remaining=%.1fs. Guidance: %s",
                resultado.motivo_bloqueio,
                pacientes,
                command.medicos_ativos,
                resultado.carga_estimada_segundos,
                command.tempo_restante_segundos,
                resultado.mensagem_explicativa,
            )

        return resultado

    async def registrar_medico_ativo(self, medico_id: UUID) -> None:
        """Adiciona médico ao plantão ativo via QueueEnginePort (RN05).

        Regras: docs/explanation/domains/queue-domain.md
        """
        await self._queue_engine.registrar_medico_ativo(medico_id)

    async def desregistrar_medico_ativo(self, medico_id: UUID) -> None:
        """Remove médico do plantão ativo via QueueEnginePort (RN05).

        Regras: docs/explanation/domains/queue-domain.md
        """
        await self._queue_engine.desregistrar_medico_ativo(medico_id)

    async def obter_medicos_ativos_count(self) -> int:
        """Retorna total de médicos ativos no plantão na plataforma (RN05).

        Regras: docs/explanation/domains/queue-domain.md
        """
        return await self._queue_engine.obter_medicos_ativos_count()
