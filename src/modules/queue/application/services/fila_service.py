"""Queue ingestion, 64-bit priority scoring, and acquisition service (RN01)."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import ValidationError
from src.modules.queue.application.dtos import (
    AdquirirProximoPacienteCommand,
    AlocacaoChamadaResult,
    AlocarChamadaCommand,
    AvaliarAdmissaoCommand,
    IngressarFilaComBackpressureCommand,
    IngressarFilaCommand,
    IngressarFilaResult,
)
from src.modules.queue.application.services.alocacao_service import (
    AlocacaoChamadaService,
)
from src.modules.queue.application.services.controle_admissao_service import (
    ControleAdmissaoService,
)
from src.modules.queue.domain.exceptions import (
    AdmissaoFilaSuspensaError,
    AtendimentoNaoDisponivelError,
    MedicoOcupadoError,
)
from src.modules.queue.domain.models import PrioridadeClinica

logger = logging.getLogger("medisync.queue.fila")

# Invariant multiplier for clinical urgency levels 1 to 5 (RN01, ADR-002)
SCORE_PRIORITY_MULTIPLIER = 1_000_000_000_000


def calcular_score_fila(
    prioridade_clinica: int | PrioridadeClinica,
    timestamp_epoch: int | float | datetime | None = None,
) -> int:
    """Calculates deterministic 64-bit score for clinical queue sorting (RN01).

    Formula:
        Score = (prioridade_clinica * 10^12) + timestamp_segundos

    Lower scores indicate higher precedence in Valkey ZSET ascending order.
    """
    prioridade_int = int(prioridade_clinica)
    if prioridade_int < 1 or prioridade_int > 5:
        raise ValidationError(
            "Prioridade clínica deve ser entre 1 e 5 (1=Emergência, 5=Não Urgente)."
        )

    if timestamp_epoch is None:
        ts_segundos = int(datetime.now(UTC).timestamp())
    elif isinstance(timestamp_epoch, datetime):
        ts_segundos = int(timestamp_epoch.timestamp())
    else:
        ts_segundos = int(timestamp_epoch)

    return (prioridade_int * SCORE_PRIORITY_MULTIPLIER) + ts_segundos


class FilaService:
    """Manages queue admission, FIFO ordering, and next patient acquisition."""

    def __init__(
        self,
        valkey: Redis,
        db_session: AsyncSession,
        alocacao_service: AlocacaoChamadaService | None = None,
        controle_admissao: ControleAdmissaoService | None = None,
    ) -> None:
        self._valkey = valkey
        self._db_session = db_session
        self._alocacao_service = alocacao_service or AlocacaoChamadaService(
            valkey=valkey,
            db_session=db_session,
        )
        self._controle_admissao = controle_admissao or ControleAdmissaoService(
            valkey=valkey
        )

    async def ingressar_fila(
        self,
        command: IngressarFilaCommand,
    ) -> IngressarFilaResult:
        """Ingests an attendance into the organization's virtual queue."""
        k_fila = f"fila:{command.organizacao_id}:aptos"
        score = calcular_score_fila(
            command.prioridade_clinica,
            command.data_entrada_fila,
        )
        atendimento_id_str = str(command.atendimento_id)

        await self._valkey.zadd(k_fila, {atendimento_id_str: score})  # pyright: ignore[reportUnknownMemberType]
        rank = await self._valkey.zrank(k_fila, atendimento_id_str)  # pyright: ignore[reportUnknownMemberType]
        posicao = (rank + 1) if isinstance(rank, int) else 1

        logger.info(
            "Attendance %s ingested into queue %s with score=%d (pos=%d)",
            atendimento_id_str,
            k_fila,
            score,
            posicao,
        )

        return IngressarFilaResult(
            atendimento_id=command.atendimento_id,
            organizacao_id=command.organizacao_id,
            score=score,
            posicao=posicao,
        )

    async def admitir_com_backpressure(
        self,
        command: IngressarFilaComBackpressureCommand,
    ) -> IngressarFilaResult:
        """Admits patient with stochastic backpressure check (RN05)."""
        pacientes_aguardando = await self.obter_tamanho_fila(command.organizacao_id)

        avaliacao_cmd = AvaliarAdmissaoCommand(
            organizacao_id=command.organizacao_id,
            medicos_ativos=command.medicos_ativos,
            tempo_restante_segundos=command.tempo_restante_segundos,
            pacientes_aguardando=pacientes_aguardando,
            total_admissoes_hoje=command.total_admissoes_hoje,
            tma_estimado_segundos=command.tma_estimado_segundos,
            alpha_margem=command.alpha_margem,
            cota_diaria_maxima=command.cota_diaria_maxima,
        )
        avaliacao = await self._controle_admissao.avaliar_admissao(avaliacao_cmd)

        if not avaliacao.admissao_permitida:
            motivo = avaliacao.motivo_bloqueio or "CAPACIDADE_EXCEDIDA"
            raise AdmissaoFilaSuspensaError(
                detail=avaliacao.mensagem_explicativa,
                motivo=motivo,
            )

        ing_cmd = IngressarFilaCommand(
            organizacao_id=command.organizacao_id,
            atendimento_id=command.atendimento_id,
            prioridade_clinica=command.prioridade_clinica,
            data_entrada_fila=command.data_entrada_fila,
        )
        return await self.ingressar_fila(ing_cmd)

    async def adquirir_proximo_paciente(
        self,
        command: AdquirirProximoPacienteCommand,
    ) -> AlocacaoChamadaResult | None:
        """Acquires next most urgent patient with in-memory retry on code -1."""
        k_fila = f"fila:{command.organizacao_id}:aptos"

        for attempt in range(command.max_retries):
            # Query top element in ZSET (O(log N))
            raw_elements = await self._valkey.zrange(k_fila, 0, 0)  # pyright: ignore[reportUnknownMemberType]
            if len(raw_elements) == 0:
                logger.info(
                    "Queue %s is empty, no patient available for doctor %s",
                    k_fila,
                    command.medico_id,
                )
                return None

            candidate_raw = raw_elements[0]
            candidate_id_str = (
                candidate_raw.decode("utf-8")
                if isinstance(candidate_raw, bytes)
                else str(candidate_raw)
            )
            candidate_uuid = UUID(candidate_id_str)

            try:
                alocar_cmd = AlocarChamadaCommand(
                    organizacao_id=command.organizacao_id,
                    medico_id=command.medico_id,
                    atendimento_id=candidate_uuid,
                    ttl_segundos=command.ttl_segundos,
                )
                return await self._alocacao_service.alocar_chamada(alocar_cmd)
            except MedicoOcupadoError:
                # Doctor is already locked with an active call -> fail immediately
                logger.warning(
                    "Doctor %s is busy, rejecting acquire_next_patient",
                    command.medico_id,
                )
                raise
            except AtendimentoNaoDisponivelError:
                # Candidate was snatched concurrently -> retry with next in queue
                logger.warning(
                    "Patient %s was snatched or unavailable during allocation race. "
                    "Retrying next patient (attempt %d/%d)...",
                    candidate_uuid,
                    attempt + 1,
                    command.max_retries,
                )
                continue

        # Exhausted retries without obtaining a patient
        msg = (
            f"Não foi possível alocar paciente para o médico '{command.medico_id}' "
            f"após {command.max_retries} tentativas devido à alta concorrência."
        )
        logger.error(msg)
        raise AtendimentoNaoDisponivelError(msg)

    # English alias as defined in architecture specification
    acquire_next_patient = adquirir_proximo_paciente

    async def remover_da_fila(
        self,
        organizacao_id: int,
        atendimento_id: UUID,
    ) -> bool:
        """Removes an attendance from the queue if present."""
        k_fila = f"fila:{organizacao_id}:aptos"
        removed = await self._valkey.zrem(k_fila, str(atendimento_id))  # pyright: ignore[reportUnknownMemberType]
        return bool(int(removed) > 0)

    async def obter_posicao_fila(
        self,
        organizacao_id: int,
        atendimento_id: UUID,
    ) -> int | None:
        """Returns 1-based position of attendance in queue, or None if not present."""
        k_fila = f"fila:{organizacao_id}:aptos"
        rank = await self._valkey.zrank(k_fila, str(atendimento_id))  # pyright: ignore[reportUnknownMemberType]
        if isinstance(rank, int):
            return rank + 1
        return None

    async def obter_tamanho_fila(self, organizacao_id: int) -> int:
        """Returns the total number of waiting patients in the queue."""
        k_fila = f"fila:{organizacao_id}:aptos"
        card = await self._valkey.zcard(k_fila)  # pyright: ignore[reportUnknownMemberType]
        return card

    async def listar_fila(
        self,
        organizacao_id: int,
        offset: int = 0,
        limit: int = 50,
    ) -> list[str]:
        """Lists attendance IDs in queue sorted by priority and arrival time."""
        k_fila = f"fila:{organizacao_id}:aptos"
        end = offset + limit - 1 if limit > 0 else -1
        raw_elements = await self._valkey.zrange(k_fila, offset, end)  # pyright: ignore[reportUnknownMemberType]
        result: list[str] = []
        for elem in raw_elements:
            if isinstance(elem, bytes):
                result.append(elem.decode("utf-8"))
            else:
                result.append(str(elem))
        return result
