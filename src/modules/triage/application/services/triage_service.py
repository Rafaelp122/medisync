from typing import TYPE_CHECKING
from uuid import UUID

from src.core.errors import ValidationError
from src.core.uuid7 import uuid7
from src.modules.triage.application.dtos import (
    TriageRiskEvaluationDTO,
)
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

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class TriageService:
    """Clinical triage evaluation and emergency admission control service."""

    def __init__(
        self,
        emergency_notifier: EmergencyNotifierPort | None = None,
        session: "AsyncSession | None" = None,
    ) -> None:
        self._notifier = emergency_notifier
        self._session = session

    async def avaliar_risco(
        self,
        organizacao_id: int,
        queixa_principal: str,
        sintomas: list[str],
        escala_dor: int = 0,
        tcle_texto: str = "",
        tcle_hash: str | None = None,
        *,
        raise_on_emergency: bool = True,
        atendimento_id: UUID | None = None,
    ) -> TriageRiskEvaluationDTO:
        """Classifica risco clínico, calcula hash do TCLE e valida SAMU 192.

        Consolida a avaliação de risco clínico (RN01), cálculo canônico do hash
        do TCLE (SHA-256) e disparo da salvaguarda SAMU 192 (RN04).
        """
        tcle_hash_final = tcle_hash.strip().lower() if tcle_hash else None
        if not tcle_hash_final:
            if tcle_texto and tcle_texto.strip():
                tcle_hash_final = calcular_hash_tcle(tcle_texto)
            else:
                raise ValidationError("Consentimento TCLE obrigatório (texto ou hash).")

        prioridade = classificar_risco_clinico(
            queixa_principal=queixa_principal,
            sintomas=sintomas,
            escala_dor=escala_dor,
        )

        if prioridade == 1:
            if self._notifier is not None:
                alerta = EmergencyAlertDTO(
                    atendimento_id=atendimento_id or uuid7(),
                    organizacao_id=organizacao_id,
                    queixa_principal=queixa_principal,
                    sintomas_alerta=sintomas,
                )
                await self._notifier.notificar_emergencia_samu(alerta)

            if raise_on_emergency:
                raise EmergenciaCriticaSamuError(
                    "Emergência médica crítica detectada (Nível 1). "
                    "Ingresso no PA Virtual bloqueado. Acione imediatamente o SAMU 192."
                )

            return TriageRiskEvaluationDTO(
                prioridade_clinica=1,
                tcle_hash=tcle_hash_final,
                alerta_samu_disparado=True,
                instrucao_redirecionamento=INSTRUCAO_SAMU_PADRAO,
            )

        return TriageRiskEvaluationDTO(
            prioridade_clinica=prioridade,
            tcle_hash=tcle_hash_final,
            alerta_samu_disparado=False,
            instrucao_redirecionamento=None,
        )

    async def registrar_triagem(
        self,
        organizacao_id: int,
        atendimento_id: UUID,
        queixa_principal: str,
        sintomas: list[str],
        prioridade_calculada: int,
        alerta_samu_disparado: bool = False,
    ) -> UUID:
        """Persiste atomicamente a entidade Triagem associada 1:1 ao atendimento."""
        if self._session is None:
            raise RuntimeError(
                "AsyncSession é necessária para persistir o registro de Triagem."
            )

        triagem = Triagem(
            organizacao_id=organizacao_id,
            atendimento_id=atendimento_id,
            queixa_principal=queixa_principal,
            prioridade_calculada=prioridade_calculada,
            sintomas_alerta=sintomas,
            alerta_samu_disparado=alerta_samu_disparado,
        )
        self._session.add(triagem)
        await self._session.flush()
        return triagem.id
