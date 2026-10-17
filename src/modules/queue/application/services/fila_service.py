"""Queue ingestion, 64-bit priority scoring, and acquisition service (RN01)."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from arq.connections import ArqRedis
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFoundError, ValidationError
from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoCommand,
    AdmissaoAtendimentoResult,
    AdquirirProximoPacienteCommand,
    AlocacaoChamadaResult,
    AlocarChamadaCommand,
    AvaliarAdmissaoCommand,
    CancelarAtendimentoResult,
    IngressarFilaComBackpressureCommand,
    IngressarFilaCommand,
    IngressarFilaResult,
    PioraClinicaCommand,
    PioraClinicaResult,
    PosicaoFilaResult,
)
from src.modules.queue.application.ports.paciente_ausente_notifier import (
    LoggingPacienteAusenteNotifier,
    PacienteAusenteEvent,
    PacienteAusenteNotifierPort,
)
from src.modules.queue.application.ports.queue_store_port import (
    AdmissaoAptoResult,
    AtendimentoSnapshotDTO,
)
from src.modules.queue.application.ports.triage_port import TriagePort
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
    TransicaoEstadoInvalidaError,
)
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import (
    TERMINAL_STATUSES,
    StatusAtendimento,
)
from src.modules.queue.domain.scoring import calcular_score

logger = logging.getLogger("medisync.queue.fila")


class FilaService:
    """Manages queue admission, FIFO ordering, and next patient acquisition."""

    def __init__(
        self,
        valkey: Redis,
        db_session: AsyncSession,
        alocacao_service: AlocacaoChamadaService,
        controle_admissao: ControleAdmissaoService | None = None,
        triage_port: TriagePort | None = None,
        arq_pool: ArqRedis | None = None,
    ) -> None:
        self._valkey = valkey
        self._db_session = db_session
        self._alocacao_service = alocacao_service
        # app->app default: ControleAdmissaoService is pure (no infra imports).
        self._controle_admissao = controle_admissao or ControleAdmissaoService(
            valkey=valkey
        )
        self._triage_port = triage_port
        self._arq_pool = arq_pool

    @property
    def controle_admissao(self) -> ControleAdmissaoService:
        """Provide admission control service."""
        return self._controle_admissao

    @property
    def arq_pool(self) -> ArqRedis | None:
        """Provide ARQ pool connection if configured."""
        return self._arq_pool

    @property
    def triage_port(self) -> TriagePort | None:
        """Provide clinical triage port if configured."""
        return self._triage_port

    async def admitir_paciente(
        self,
        command: AdmissaoAtendimentoCommand,
        *,
        raise_on_emergency: bool = True,
    ) -> AdmissaoAtendimentoResult:
        """Executes full clinical admission workflow (RN01, RN04, RN05, RN07)."""
        if command.organizacao_id <= 0:
            raise ValidationError("organizacao_id deve ser positivo.")

        if self._triage_port is None:
            raise RuntimeError("TriagePort não configurado no FilaService.")

        # 1. Clinical risk assessment and SAMU 192 safeguard
        # via TriagePort (RN01, RN04, RN07)
        triage_eval = await self._triage_port.avaliar_risco(
            organizacao_id=command.organizacao_id,
            queixa_principal=command.queixa_principal,
            sintomas=command.sintomas,
            escala_dor=command.escala_dor,
            tcle_texto=command.tcle_texto,
            tcle_hash=command.tcle_hash,
            raise_on_emergency=raise_on_emergency,
        )

        # 2. Stochastic backpressure evaluation (RN05)
        pacientes_aguardando = await self.obter_tamanho_fila(command.organizacao_id)
        total_admissoes_hoje = await self._controle_admissao.obter_admissoes_hoje(
            command.organizacao_id
        )
        avaliacao_cmd = AvaliarAdmissaoCommand(
            organizacao_id=command.organizacao_id,
            medicos_ativos=command.medicos_ativos,
            tempo_restante_segundos=command.tempo_restante_segundos,
            pacientes_aguardando=pacientes_aguardando,
            total_admissoes_hoje=total_admissoes_hoje,
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

        # 3. Atomic persistence of Atendimento + Triagem aggregate
        atendimento = Atendimento(
            organizacao_id=command.organizacao_id,
            paciente_id=command.paciente_id,
            prioridade_clinica=triage_eval.prioridade_clinica,
            tcle_hash=triage_eval.tcle_hash,
            status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        )
        self._db_session.add(atendimento)
        await self._db_session.flush()

        triagem_id = await self._triage_port.registrar_triagem(
            organizacao_id=command.organizacao_id,
            atendimento_id=atendimento.id,
            queixa_principal=command.queixa_principal,
            sintomas=command.sintomas,
            prioridade_calculada=triage_eval.prioridade_clinica,
            alerta_samu_disparado=triage_eval.alerta_samu_disparado,
        )

        await self._db_session.commit()
        await self._db_session.refresh(atendimento)

        # Increment daily admission quota atomically in Valkey (RN05 / NC-QUE-01)
        await self._controle_admissao.incrementar_admissoes_hoje(command.organizacao_id)

        # 4. Schedule asynchronous eligibility verification in ARQ worker
        # (NC-BIL-01, RF-02)
        if self._arq_pool is not None:
            await self._arq_pool.enqueue_job(
                "validar_elegibilidade_task",
                organizacao_id=command.organizacao_id,
                atendimento_id=str(atendimento.id),
                paciente_id=str(command.paciente_id),
                cpf=command.cpf,
                cns=command.cns,
                operadora_id=command.operadora_id,
                numero_carteirinha=command.numero_carteirinha,
                _job_id=f"elegibilidade:{atendimento.id}",
            )
            logger.info(
                "Enqueued validar_elegibilidade_task for attendance %s in ARQ pool",
                atendimento.id,
            )

        logger.info(
            "Patient %s admitted to attendance %s with triage %s (priority=%d)",
            command.paciente_id,
            atendimento.id,
            triagem_id,
            triage_eval.prioridade_clinica,
        )

        return AdmissaoAtendimentoResult(
            atendimento_id=atendimento.id,
            triagem_id=triagem_id,
            organizacao_id=command.organizacao_id,
            paciente_id=command.paciente_id,
            status_atendimento=str(atendimento.status),
            prioridade_clinica=triage_eval.prioridade_clinica,
            alerta_samu_disparado=triage_eval.alerta_samu_disparado,
            instrucoes=triage_eval.instrucao_redirecionamento,
        )

    async def ingressar_fila(
        self,
        command: IngressarFilaCommand,
    ) -> IngressarFilaResult:
        """Ingests an attendance into the organization's virtual queue."""
        k_fila = f"fila:{command.organizacao_id}:aptos"
        score = calcular_score(
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
                    "Doctor %s is busy, rejecting adquirir_proximo_paciente",
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

    async def admitir_atendimento_apto(
        self,
        organizacao_id: int,
        atendimento_id: UUID,
    ) -> AdmissaoAptoResult:
        """Promote attendance to APTO_PARA_CHAMADA in DB and ingest into queue."""
        atendimento = await self._db_session.get(Atendimento, atendimento_id)
        if atendimento is None or atendimento.organizacao_id != organizacao_id:
            raise NotFoundError(
                f"Atendimento '{atendimento_id}' não encontrado na "
                f"organização {organizacao_id}."
            )

        if (
            atendimento.status
            == StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE.value
        ):
            atendimento.promover_para_apto()
            await self._db_session.commit()
            await self._db_session.refresh(atendimento)

            ts_base = atendimento.data_entrada_fila or atendimento.criado_em
            score = calcular_score(atendimento.prioridade_clinica, ts_base)
            k_fila = f"fila:{organizacao_id}:aptos"
            await self._valkey.zadd(k_fila, {str(atendimento_id): score})  # pyright: ignore[reportUnknownMemberType]
            logger.info(
                "Attendance %s promoted to APTO and ingested into %s with score=%d",
                atendimento_id,
                k_fila,
                score,
            )
            return AdmissaoAptoResult(promovido=True, status="aprovado", score=score)

        ts_base = atendimento.data_entrada_fila or atendimento.criado_em
        score = calcular_score(atendimento.prioridade_clinica, ts_base)
        return AdmissaoAptoResult(
            promovido=False, status=str(atendimento.status), score=score
        )

    async def resolver_ring_timeout(
        self,
        organizacao_id: int,
        atendimento_id: UUID,
        medico_id: UUID,
        notifier: PacienteAusenteNotifierPort | None = None,
    ) -> str:
        """Deterministic 45s ring timeout resolution (RN02)."""
        atend_id_str = str(atendimento_id)
        med_id_str = str(medico_id)
        k_medico_ring = f"lock:{organizacao_id}:medico:{med_id_str}"
        k_atend_ring = f"lock:{organizacao_id}:atendimento:{atend_id_str}"
        k_medico_consulta = f"lock:{organizacao_id}:consulta_ativa:medico:{med_id_str}"

        atendimento = await self._db_session.get(
            Atendimento, atendimento_id, with_for_update=True
        )
        if atendimento is None or atendimento.organizacao_id != organizacao_id:
            logger.warning(
                "Ring timeout task: attendance %s not found in org=%d",
                atendimento_id,
                organizacao_id,
            )
            return "not_found"

        current_status = atendimento.status

        if current_status == StatusAtendimento.CHAMANDO_PACIENTE.value:
            atendimento.registrar_ausencia_paciente()
            await self._db_session.commit()

            async with self._valkey.pipeline(transaction=True) as pipe:
                pipe.delete(k_medico_ring)
                pipe.delete(k_atend_ring)
                await pipe.execute()

            dispatch_notifier = notifier or LoggingPacienteAusenteNotifier()
            event = PacienteAusenteEvent(
                atendimento_id=atendimento.id,
                organizacao_id=organizacao_id,
                medico_id=medico_id,
                paciente_id=atendimento.paciente_id,
                tempo_toque_segundos=45,
            )
            await dispatch_notifier.emitir_paciente_ausente(event)
            logger.info(
                "Patient absent (no-show) recorded for attendance %s (medico=%s)",
                atendimento_id,
                medico_id,
            )
            return "no_show_recorded"

        if current_status == StatusAtendimento.EM_ATENDIMENTO.value:
            async with self._valkey.pipeline(transaction=True) as pipe:
                pipe.delete(k_atend_ring)
                pipe.delete(k_medico_ring)
                pipe.set(k_medico_consulta, atend_id_str, ex=7200)
                await pipe.execute()
            logger.info(
                "Call answered for attendance %s; promoted active lock",
                atendimento_id,
            )
            return "active_consultation_preserved"

        # Any terminal state or cancelled -> clean up locks
        async with self._valkey.pipeline(transaction=True) as pipe:
            pipe.delete(k_medico_ring)
            pipe.delete(k_atend_ring)
            await pipe.execute()
        return "already_finalized"

    async def atender_chamada(
        self,
        atendimento_id: UUID,
    ) -> None:
        """Transition attendance in CHAMANDO_PACIENTE to EM_ATENDIMENTO.

        Commits DB session, and atomically promotes Valkey doctor ring lock
        to active consultation (7200s). Idempotent if already in EM_ATENDIMENTO.
        """
        atendimento = await self._db_session.get(
            Atendimento, atendimento_id, with_for_update=True
        )
        if atendimento is None:
            raise NotFoundError(f"Atendimento '{atendimento_id}' não encontrado.")

        if atendimento.status == StatusAtendimento.EM_ATENDIMENTO.value:
            if atendimento.medico_id is not None:
                k_medico_consulta = (
                    f"lock:{atendimento.organizacao_id}:consulta_ativa:medico:"
                    f"{atendimento.medico_id}"
                )
                await self._valkey.set(k_medico_consulta, str(atendimento.id), ex=7200)
            return

        if atendimento.status != StatusAtendimento.CHAMANDO_PACIENTE.value:
            raise TransicaoEstadoInvalidaError(
                f"Apenas atendimentos em '{StatusAtendimento.CHAMANDO_PACIENTE}' "
                f"podem ser atendidos. Estado atual: '{atendimento.status}'."
            )

        atendimento.atender_chamada()
        await self._db_session.commit()

        if atendimento.medico_id is not None:
            k_medico_ring = (
                f"lock:{atendimento.organizacao_id}:medico:{atendimento.medico_id}"
            )
            k_atend_ring = (
                f"lock:{atendimento.organizacao_id}:atendimento:{atendimento.id}"
            )
            k_medico_consulta = (
                f"lock:{atendimento.organizacao_id}:consulta_ativa:medico:"
                f"{atendimento.medico_id}"
            )
            async with self._valkey.pipeline(transaction=True) as pipe:
                pipe.delete(k_medico_ring)
                pipe.delete(k_atend_ring)
                pipe.set(k_medico_consulta, str(atendimento.id), ex=7200)
                await pipe.execute()

    async def concluir_atendimento(
        self,
        atendimento_id: UUID,
    ) -> None:
        """Transition attendance in EM_ATENDIMENTO to CONCLUIDO and persist."""
        atendimento = await self._db_session.get(Atendimento, atendimento_id)
        if atendimento is None:
            raise NotFoundError(f"Atendimento '{atendimento_id}' não encontrado.")

        if atendimento.status != StatusAtendimento.CONCLUIDO.value:
            atendimento.concluir_atendimento()
            await self._db_session.commit()

    async def reconciliar_fila_orfaos(
        self,
        organizacao_id: int,
        cutoff_em: datetime,
    ) -> tuple[int, list[str]]:
        """Find orphan APTO attendances missing in Valkey and reinject them into ZSET.

        Returns (scanned_count, reconciled_ids).
        """
        k_fila = f"fila:{organizacao_id}:aptos"
        stmt = (
            select(Atendimento)
            .where(
                Atendimento.organizacao_id == organizacao_id,
                Atendimento.status == StatusAtendimento.APTO_PARA_CHAMADA.value,
                Atendimento.atualizado_em <= cutoff_em,
            )
            .order_by(Atendimento.criado_em.asc())
        )
        res = await self._db_session.execute(stmt)
        candidates = res.scalars().all()

        total_scanned = len(candidates)
        reconciled_ids: list[str] = []
        for atend in candidates:
            atend_id_str = str(atend.id)

            # 1. Check if already present in Valkey ZSET
            existing_score = await self._valkey.zscore(  # pyright: ignore[reportUnknownMemberType]
                k_fila, atend_id_str
            )
            if existing_score is not None:
                continue

            # 2. Check if active ring lock exists
            k_atend_ring = f"lock:{organizacao_id}:atendimento:{atend_id_str}"
            has_ring_lock = bool(
                await self._valkey.exists(k_atend_ring)  # pyright: ignore[reportUnknownMemberType]
            )
            if has_ring_lock:
                continue

            # 3. Check if active consultation lock exists for assigned doctor
            if atend.medico_id is not None:
                med_id_str = str(atend.medico_id)
                k_medico_ring = f"lock:{organizacao_id}:medico:{med_id_str}"
                k_medico_active = (
                    f"lock:{organizacao_id}:consulta_ativa:medico:{med_id_str}"
                )
                med_ring_val = await self._valkey.get(k_medico_ring)  # pyright: ignore[reportUnknownMemberType]
                med_active_val = await self._valkey.get(k_medico_active)  # pyright: ignore[reportUnknownMemberType]
                if (
                    med_ring_val == atend_id_str.encode()
                    or med_ring_val == atend_id_str
                    or med_active_val == atend_id_str.encode()
                    or med_active_val == atend_id_str
                ):
                    continue

            # 4. Truly orphaned -> recalculate score and reinject into ZSET
            ts_base = atend.data_entrada_fila or atend.criado_em
            score = calcular_score(atend.prioridade_clinica, ts_base)
            await self._valkey.zadd(k_fila, {atend_id_str: score})  # pyright: ignore[reportUnknownMemberType]
            reconciled_ids.append(atend_id_str)
            logger.warning(
                "Sweeper restored orphan attendance %s to %s with score=%d",
                atend_id_str,
                k_fila,
                score,
            )

        return total_scanned, reconciled_ids

    async def buscar_atendimento(
        self,
        atendimento_id: UUID,
    ) -> AtendimentoSnapshotDTO | None:
        """Fetch attendance snapshot by ID using chainable ORM select."""
        stmt = select(Atendimento).where(Atendimento.id == atendimento_id)
        res = await self._db_session.execute(stmt)
        atend = res.scalar_one_or_none()
        if atend is None:
            return None
        return AtendimentoSnapshotDTO(
            id=atend.id,
            organizacao_id=atend.organizacao_id,
            paciente_id=atend.paciente_id,
            medico_id=atend.medico_id,
            status=atend.status,
            prioridade_clinica=int(atend.prioridade_clinica),
            tcle_hash=atend.tcle_hash,
            data_entrada_fila=atend.data_entrada_fila,
            criado_em=atend.criado_em,
            is_terminal=atend.status in TERMINAL_STATUSES,
        )

    async def obter_posicao_e_estimativa(
        self,
        organizacao_id: int,
        atendimento_id: UUID,
    ) -> PosicaoFilaResult:
        """Returns real-time queue position and estimated wait time in seconds."""
        atendimento = await self._db_session.get(Atendimento, atendimento_id)
        if atendimento is None or atendimento.organizacao_id != organizacao_id:
            raise NotFoundError(
                f"Atendimento '{atendimento_id}' não encontrado na "
                f"organização {organizacao_id}."
            )

        total_aguardando = await self.obter_tamanho_fila(organizacao_id)
        status_atual = str(atendimento.status)

        if atendimento.is_finalizado:
            return PosicaoFilaResult(
                atendimento_id=atendimento_id,
                status=status_atual,
                posicao=None,
                total_aguardando=total_aguardando,
                tempo_estimado_segundos=None,
            )

        if status_atual in (
            StatusAtendimento.CHAMANDO_PACIENTE.value,
            StatusAtendimento.EM_ATENDIMENTO.value,
        ):
            return PosicaoFilaResult(
                atendimento_id=atendimento_id,
                status=status_atual,
                posicao=0,
                total_aguardando=total_aguardando,
                tempo_estimado_segundos=0,
            )

        posicao = await self.obter_posicao_fila(organizacao_id, atendimento_id)
        medicos_ativos = await self._controle_admissao.obter_medicos_ativos_count(
            organizacao_id
        )
        medicos_div = max(medicos_ativos, 1)

        tempo_estimado: int | None = None
        if posicao is not None:
            # TMA estimado padrão = 600 segundos (10 minutos)
            tempo_estimado = int((posicao * 600) / medicos_div)

        return PosicaoFilaResult(
            atendimento_id=atendimento_id,
            status=status_atual,
            posicao=posicao,
            total_aguardando=total_aguardando,
            tempo_estimado_segundos=tempo_estimado,
        )

    async def cancelar_atendimento_paciente(
        self,
        organizacao_id: int,
        atendimento_id: UUID,
        motivo: str | None = None,
    ) -> CancelarAtendimentoResult:
        """Cancels an attendance voluntary by the patient (RN06)."""
        atendimento = await self._db_session.get(Atendimento, atendimento_id)
        if atendimento is None or atendimento.organizacao_id != organizacao_id:
            raise NotFoundError(
                f"Atendimento '{atendimento_id}' não encontrado na "
                f"organização {organizacao_id}."
            )

        atendimento.cancelar_pelo_paciente(motivo)
        await self.remover_da_fila(organizacao_id, atendimento_id)
        if atendimento.medico_id:
            await self._alocacao_service.liberar_locks(
                organizacao_id=organizacao_id,
                medico_id=atendimento.medico_id,
                atendimento_id=atendimento_id,
            )

        await self._db_session.commit()
        await self._db_session.refresh(atendimento)

        now = atendimento.atualizado_em or datetime.now(UTC)
        logger.info(
            "Attendance %s cancelled by patient in org %d (motivo=%s)",
            atendimento_id,
            organizacao_id,
            motivo,
        )
        return CancelarAtendimentoResult(
            atendimento_id=atendimento_id,
            status=str(atendimento.status),
            cancelado_em=now,
            motivo=motivo,
        )

    async def processar_piora_clinica(
        self,
        command: PioraClinicaCommand,
    ) -> PioraClinicaResult:
        """Re-evaluates symptoms upon patient clinical deterioration report (RF-06)."""
        if self._triage_port is None:
            raise RuntimeError("TriagePort não configurado no FilaService.")

        atendimento = await self._db_session.get(Atendimento, command.atendimento_id)
        if atendimento is None or atendimento.organizacao_id != command.organizacao_id:
            raise NotFoundError(
                f"Atendimento '{command.atendimento_id}' não encontrado na "
                f"organização {command.organizacao_id}."
            )

        if (
            atendimento.is_finalizado
            or atendimento.status == StatusAtendimento.EM_ATENDIMENTO.value
        ):
            raise TransicaoEstadoInvalidaError(
                f"Não é possível acionar piora clínica para atendimento "
                f"no estado '{atendimento.status}'."
            )

        triage_eval = await self._triage_port.avaliar_risco(
            organizacao_id=command.organizacao_id,
            queixa_principal=command.queixa_adicional
            or "Piora de sintomas na fila virtual",
            sintomas=command.novos_sintomas,
            escala_dor=command.escala_dor,
            tcle_hash=atendimento.tcle_hash,
            raise_on_emergency=False,
            atendimento_id=atendimento.id,
        )

        if triage_eval.alerta_samu_disparado or triage_eval.prioridade_clinica == 1:
            # Escape emergencial SAMU 192 (RF-06 / RN04)
            atendimento.cancelar_pelo_paciente("ENCAMINHADO_SAMU_PIORA_CLINICA")
            await self.remover_da_fila(command.organizacao_id, command.atendimento_id)
            if atendimento.medico_id:
                await self._alocacao_service.liberar_locks(
                    organizacao_id=command.organizacao_id,
                    medico_id=atendimento.medico_id,
                    atendimento_id=command.atendimento_id,
                )
            await self._db_session.commit()
            await self._db_session.refresh(atendimento)

            instrucoes = (
                triage_eval.instrucao_redirecionamento
                or "Sinais de gravidade identificados. Ligue 192 imediatamente "
                "ou procure a emergência mais próxima."
            )
            logger.warning(
                "Patient %s reported severe deterioration in attendance %s. "
                "Dispatched SAMU escape.",
                atendimento.paciente_id,
                atendimento.id,
            )
            return PioraClinicaResult(
                atendimento_id=command.atendimento_id,
                prioridade_clinica=1,
                alerta_samu_disparado=True,
                redirecionado_emergencia=True,
                nova_posicao=None,
                instrucoes=instrucoes,
            )

        # Reclassificação de prioridade (se mais urgente, valor numérico menor)
        nova_prioridade = triage_eval.prioridade_clinica
        if nova_prioridade < atendimento.prioridade_clinica:
            atendimento.atualizar_prioridade(nova_prioridade)

        # Recalcula score no Sorted Set (ZSET) se estiver em fila
        nova_pos: int | None = None
        if atendimento.status == StatusAtendimento.APTO_PARA_CHAMADA.value:
            ts_base = atendimento.data_entrada_fila or atendimento.criado_em
            score = calcular_score(nova_prioridade, ts_base)
            k_fila = f"fila:{command.organizacao_id}:aptos"
            await self._valkey.zadd(k_fila, {str(command.atendimento_id): score})  # pyright: ignore[reportUnknownMemberType]
            nova_pos = await self.obter_posicao_fila(
                command.organizacao_id, command.atendimento_id
            )

        await self._db_session.commit()
        await self._db_session.refresh(atendimento)

        logger.info(
            "Attendance %s reclassified to priority %d (new position=%s)",
            atendimento.id,
            nova_prioridade,
            nova_pos,
        )
        return PioraClinicaResult(
            atendimento_id=command.atendimento_id,
            prioridade_clinica=nova_prioridade,
            alerta_samu_disparado=False,
            redirecionado_emergencia=False,
            nova_posicao=nova_pos,
            instrucoes="Prioridade recalculada com sucesso na fila de espera.",
        )
