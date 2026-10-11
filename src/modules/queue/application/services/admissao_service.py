"""Application service coordinating clinical triage and attendance admission."""

import logging
from typing import TYPE_CHECKING

from arq.connections import ArqRedis

from src.core.errors import ValidationError
from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoCommand,
    AdmissaoAtendimentoResult,
    AvaliarAdmissaoCommand,
)
from src.modules.queue.application.ports.triage_port import TriagePort
from src.modules.queue.application.services.controle_admissao_service import (
    ControleAdmissaoService,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.exceptions import AdmissaoFilaSuspensaError
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import StatusAtendimento

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("medisync.queue.admissao")


class AdmissaoAtendimentoService:
    """Orchestrates intake, clinical risk assessment, and atomic persistence."""

    def __init__(
        self,
        session: "AsyncSession",
        fila_service: FilaService,
        triage_port: TriagePort,
        controle_admissao: ControleAdmissaoService | None = None,
        arq_pool: ArqRedis | None = None,
    ) -> None:
        self._session = session
        self._fila_service = fila_service
        self._triage_port = triage_port
        self._controle_admissao = controle_admissao or fila_service.controle_admissao
        self._arq_pool = arq_pool

    async def admitir_paciente(
        self,
        command: AdmissaoAtendimentoCommand,
        *,
        raise_on_emergency: bool = True,
    ) -> AdmissaoAtendimentoResult:
        """Executes full clinical admission workflow."""
        if command.organizacao_id <= 0:
            raise ValidationError("organizacao_id deve ser positivo.")

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
        pacientes_aguardando = await self._fila_service.obter_tamanho_fila(
            command.organizacao_id
        )
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
        self._session.add(atendimento)
        await self._session.flush()

        triagem_id = await self._triage_port.registrar_triagem(
            organizacao_id=command.organizacao_id,
            atendimento_id=atendimento.id,
            queixa_principal=command.queixa_principal,
            sintomas=command.sintomas,
            prioridade_calculada=triage_eval.prioridade_clinica,
            alerta_samu_disparado=triage_eval.alerta_samu_disparado,
        )

        await self._session.commit()
        await self._session.refresh(atendimento)

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
            status_atendimento=atendimento.status,
            prioridade_clinica=triage_eval.prioridade_clinica,
            alerta_samu_disparado=triage_eval.alerta_samu_disparado,
            instrucoes=triage_eval.instrucao_redirecionamento,
        )
