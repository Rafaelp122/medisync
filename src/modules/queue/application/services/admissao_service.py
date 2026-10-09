"""Application service coordinating clinical triage and attendance admission."""

import logging
from typing import TYPE_CHECKING

from src.core.errors import ValidationError
from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoCommand,
    AdmissaoAtendimentoResult,
    AvaliarAdmissaoCommand,
)
from src.modules.queue.application.services.controle_admissao_service import (
    ControleAdmissaoService,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.exceptions import AdmissaoFilaSuspensaError
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.modules.triage.domain.classification import (
    calcular_hash_tcle,
    classificar_risco_clinico,
)
from src.modules.triage.domain.exceptions import EmergenciaCriticaSamuError
from src.modules.triage.domain.models.triagem import Triagem

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("medisync.queue.admissao")


class AdmissaoAtendimentoService:
    """Orchestrates intake, clinical risk assessment, and atomic persistence."""

    def __init__(
        self,
        session: "AsyncSession",
        fila_service: FilaService,
        controle_admissao: ControleAdmissaoService | None = None,
    ) -> None:
        self._session = session
        self._fila_service = fila_service
        self._controle_admissao = controle_admissao or fila_service.controle_admissao

    async def admitir_paciente(
        self,
        command: AdmissaoAtendimentoCommand,
        *,
        raise_on_emergency: bool = True,
    ) -> AdmissaoAtendimentoResult:
        """Executes full clinical admission workflow."""
        if command.organizacao_id <= 0:
            raise ValidationError("organizacao_id deve ser positivo.")

        # 1. Resolve TCLE hash (RN07, LGPD Art. 11)
        tcle_hash_final = command.tcle_hash
        if not tcle_hash_final:
            if command.tcle_texto:
                tcle_hash_final = calcular_hash_tcle(command.tcle_texto)
            else:
                raise ValidationError("Consentimento TCLE obrigatório (texto ou hash).")

        # 2. Risk classification via Manchester / ACR Protocol (RN01)
        prioridade = classificar_risco_clinico(
            queixa_principal=command.queixa_principal,
            sintomas=command.sintomas,
            escala_dor=command.escala_dor,
        )

        # 3. Emergency Safeguard (RN04)
        if prioridade == 1 and raise_on_emergency:
            logger.critical(
                "Critical emergency (Nível 1) in org %d for patient %s",
                command.organizacao_id,
                command.paciente_id,
            )
            raise EmergenciaCriticaSamuError(
                "Emergência médica crítica detectada (Nível 1). "
                "Ingresso no PA Virtual bloqueado. Acione imediatamente o SAMU 192."
            )

        # 4. Stochastic backpressure evaluation (RN05)
        pacientes_aguardando = await self._fila_service.obter_tamanho_fila(
            command.organizacao_id
        )
        avaliacao_cmd = AvaliarAdmissaoCommand(
            organizacao_id=command.organizacao_id,
            medicos_ativos=command.medicos_ativos,
            tempo_restante_segundos=command.tempo_restante_segundos,
            pacientes_aguardando=pacientes_aguardando,
            total_admissoes_hoje=0,
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

        # 5. Atomic persistence of Atendimento + Triagem
        atendimento = Atendimento(
            organizacao_id=command.organizacao_id,
            paciente_id=command.paciente_id,
            prioridade_clinica=prioridade,
            tcle_hash=tcle_hash_final,
            status=StatusAtendimento.TRIADO_AGUARDANDO_ELEGIBILIDADE,
        )
        self._session.add(atendimento)
        await self._session.flush()

        triagem = Triagem(
            organizacao_id=command.organizacao_id,
            atendimento_id=atendimento.id,
            queixa_principal=command.queixa_principal,
            prioridade_calculada=prioridade,
            sintomas_alerta=command.sintomas,
            alerta_samu_disparado=(prioridade == 1),
        )
        self._session.add(triagem)
        await self._session.commit()
        await self._session.refresh(atendimento)
        await self._session.refresh(triagem)

        logger.info(
            "Patient %s admitted to attendance %s with triage %s (priority=%d)",
            command.paciente_id,
            atendimento.id,
            triagem.id,
            prioridade,
        )

        return AdmissaoAtendimentoResult(
            atendimento_id=atendimento.id,
            triagem_id=triagem.id,
            organizacao_id=command.organizacao_id,
            paciente_id=command.paciente_id,
            status_atendimento=atendimento.status,
            prioridade_clinica=prioridade,
            alerta_samu_disparado=(prioridade == 1),
            instrucoes=None,
        )
