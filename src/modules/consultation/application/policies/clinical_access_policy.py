"""Contextual Clinical ABAC/ReBAC authorization policy service (Tier 3).

Enforces CFM Resolution 2.314/2022, CFM Resolution 1.821/2007, and LGPD:
1. Patient digital TCLE acceptance (tcle_hash IS NOT NULL).
2. Active encounter status (EM_ATENDIMENTO or CHAMANDO_PACIENTE).
3. Strict physician assignment (current_medico_id == atendimento.medico_id).
"""

from uuid import UUID

from src.core.errors import ForbiddenError, NotFoundError
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoReaderPort,
)

_READ_ALLOWED_STATUSES = frozenset({"EM_ATENDIMENTO", "CHAMANDO_PACIENTE", "CONCLUIDO"})
_MUTATION_ALLOWED_STATUSES = frozenset({"EM_ATENDIMENTO", "CHAMANDO_PACIENTE"})


class ClinicalAccessPolicy:
    """Evaluates deontological and clinical access control rules for medical records."""

    @staticmethod
    async def validar_acesso_clinico(
        atendimento_id: UUID,
        medico_id: UUID,
        reader: AtendimentoReaderPort,
        *,
        is_mutation: bool = False,
    ) -> None:
        """Evaluate Tier 3 ABAC/ReBAC conditions for a physician accessing records.

        Raises:
            NotFoundError: If attendance does not exist.
            ForbiddenError: If TCLE is missing, status is not allowed for the operation,
                or physician does not match.
        """
        resumo = await reader.obter_resumo(atendimento_id)

        if resumo is None:
            raise NotFoundError(f"Atendimento '{atendimento_id}' não encontrado.")

        # 1. Patient TCLE Acceptance (CFM 2.314/2022 - Art. 4º)
        tcle_hash = resumo.tcle_hash
        if not tcle_hash or not str(tcle_hash).strip():
            raise ForbiddenError(
                "Acesso negado: Termo de Consentimento Livre e Esclarecido (TCLE) "
                "digital não assinado pelo paciente (Resolução CFM nº 2.314/2022)."
            )

        # 2. Strict Physician-Patient Assignment (CFM 1.821/2007 e 2.314/2022)
        atend_medico_id = resumo.medico_id
        if atend_medico_id is None or str(atend_medico_id) != str(medico_id):
            raise ForbiddenError(
                "Acesso negado: o médico autenticado não é o profissional assistente "
                "responsável por este atendimento clínico (CFM nº 2.314/2022)."
            )

        # 3. Encounter Lifecycle (active vs concluded reading)
        status = resumo.status
        allowed_statuses = (
            _MUTATION_ALLOWED_STATUSES if is_mutation else _READ_ALLOWED_STATUSES
        )
        if status not in allowed_statuses:
            if is_mutation and status == "CONCLUIDO":
                raise ForbiddenError(
                    "Acesso negado: não é permitido alterar dados clínicos "
                    "em atendimento já concluído (Resolução CFM nº 2.314/2022)."
                )
            operacao = "alterado" if is_mutation else "visualizado"
            raise ForbiddenError(
                f"Acesso negado: prontuário só pode ser {operacao} "
                f"durante atendimento ativo. Status atual do atendimento: '{status}'."
            )
