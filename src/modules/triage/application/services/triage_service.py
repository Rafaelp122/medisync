"""Triage evaluation service enforcing clinical safety and SAMU escape (RN04)."""

from dataclasses import dataclass
from uuid import UUID

from src.modules.triage.application.ports.emergency_notifier import (
    INSTRUCAO_SAMU_PADRAO,
    EmergencyAlertDTO,
    EmergencyNotifierPort,
)
from src.modules.triage.domain.classification import (
    calcular_hash_tcle,
    classificar_risco_clinico,
)
from src.modules.triage.domain.exceptions import EmergenciaCriticaSamuError
from src.modules.triage.domain.models.triagem import Triagem


@dataclass(frozen=True)
class ResultadoTriagemDTO:
    """Outcome of clinical triage assessment."""

    triagem: Triagem
    prioridade_clinica: int
    tcle_hash: str
    admissao_bloqueada: bool
    alerta_samu_disparado: bool
    instrucao_redirecionamento: str | None = None


class TriageService:
    """Clinical triage evaluation and emergency admission control service."""

    def __init__(self, emergency_notifier: EmergencyNotifierPort | None = None) -> None:
        self._notifier = emergency_notifier

    async def avaliar_e_submeter_triagem(
        self,
        organizacao_id: int,
        atendimento_id: UUID,
        queixa_principal: str,
        sintomas: list[str],
        escala_dor: int = 0,
        tcle_termo_texto: str = "",
        *,
        raise_on_emergency: bool = True,
    ) -> ResultadoTriagemDTO:
        """Avalia risco clínico, gera hash do TCLE e aplica salvaguarda SAMU 192."""
        prioridade = classificar_risco_clinico(
            queixa_principal=queixa_principal,
            sintomas=sintomas,
            escala_dor=escala_dor,
        )

        tcle_hash = calcular_hash_tcle(tcle_termo_texto) if tcle_termo_texto else ""

        triagem = Triagem(
            organizacao_id=organizacao_id,
            atendimento_id=atendimento_id,
            queixa_principal=queixa_principal,
            prioridade_calculada=prioridade,
            sintomas_alerta=sintomas,
        )

        # Salvaguarda de Deterioração / Emergência Crítica Nível 1 (RN04)
        if prioridade == 1:
            triagem.disparar_alerta_samu()

            if self._notifier:
                alerta = EmergencyAlertDTO(
                    atendimento_id=atendimento_id,
                    organizacao_id=organizacao_id,
                    queixa_principal=queixa_principal,
                    sintomas_alerta=triagem.sintomas_alerta,
                )
                await self._notifier.notificar_emergencia_samu(alerta)

            if raise_on_emergency:
                raise EmergenciaCriticaSamuError(
                    "Emergência médica crítica detectada (Nível 1). "
                    "Ingresso no PA Virtual bloqueado. Acione imediatamente o SAMU 192."
                )

            return ResultadoTriagemDTO(
                triagem=triagem,
                prioridade_clinica=1,
                tcle_hash=tcle_hash,
                admissao_bloqueada=True,
                alerta_samu_disparado=True,
                instrucao_redirecionamento=INSTRUCAO_SAMU_PADRAO,
            )

        return ResultadoTriagemDTO(
            triagem=triagem,
            prioridade_clinica=prioridade,
            tcle_hash=tcle_hash,
            admissao_bloqueada=False,
            alerta_samu_disparado=False,
            instrucao_redirecionamento=None,
        )
