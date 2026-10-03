"""Contextual Clinical ABAC/ReBAC authorization policy service (Tier 3).

Enforces CFM Resolution 2.314/2022, CFM Resolution 1.821/2007, and LGPD:
1. Patient digital TCLE acceptance (tcle_hash IS NOT NULL).
2. Active encounter status (EM_ATENDIMENTO or CHAMANDO_PACIENTE).
3. Strict physician assignment (current_medico_id == atendimento.medico_id).
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import ForbiddenError, NotFoundError

_ACTIVE_STATUSES = frozenset({"EM_ATENDIMENTO", "CHAMANDO_PACIENTE"})


class ClinicalAccessPolicy:
    """Evaluates deontological and clinical access control rules for medical records."""

    @staticmethod
    async def validar_acesso_clinico(
        atendimento_id: UUID,
        medico_id: UUID,
        session: AsyncSession,
    ) -> None:
        """Evaluate Tier 3 ABAC/ReBAC conditions for a physician accessing records.

        Raises:
            NotFoundError: If attendance does not exist.
            ForbiddenError: If TCLE is missing, status is not active,
                or physician does not match.
        """
        stmt = text(
            """
            SELECT id, organizacao_id, medico_id, status, tcle_hash
            FROM atendimentos
            WHERE id = :atend_id
            """
        )
        result = await session.execute(stmt, {"atend_id": atendimento_id})
        row = result.mappings().one_or_none()

        if row is None:
            raise NotFoundError(f"Atendimento '{atendimento_id}' não encontrado.")

        # 1. Patient TCLE Acceptance (CFM 2.314/2022 - Art. 4º)
        tcle_hash = row["tcle_hash"]
        if not tcle_hash or not str(tcle_hash).strip():
            raise ForbiddenError(
                "Acesso negado: Termo de Consentimento Livre e Esclarecido (TCLE) "
                "digital não assinado pelo paciente (Resolução CFM nº 2.314/2022)."
            )

        # 2. Strict Physician-Patient Assignment (CFM 1.821/2007 e 2.314/2022)
        atend_medico_id = row["medico_id"]
        if atend_medico_id is None or str(atend_medico_id) != str(medico_id):
            raise ForbiddenError(
                "Acesso negado: o médico autenticado não é o profissional assistente "
                "responsável por este atendimento clínico (CFM nº 2.314/2022)."
            )

        # 3. Active Encounter Lifecycle (EM_ATENDIMENTO or CHAMANDO_PACIENTE)
        status = str(row["status"]).strip().upper()
        if status not in _ACTIVE_STATUSES:
            raise ForbiddenError(
                f"Acesso negado: prontuário só pode ser visualizado ou alterado "
                f"durante atendimento ativo. Status atual do atendimento: '{status}'."
            )
