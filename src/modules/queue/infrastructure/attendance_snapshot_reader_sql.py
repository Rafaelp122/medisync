"""Read-only lightweight SQL adapter for attendance snapshots across modules."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.queue.application.ports.queue_store_port import (
    AtendimentoSnapshotDTO,
)
from src.modules.queue.domain.enums import TERMINAL_STATUSES
from src.modules.queue.domain.models.atendimento import Atendimento


class SqlAttendanceSnapshotReader:
    """Leitor SQL read-only leve de atendimentos sem dependência de Valkey/Triage.

    Regras: ADR-001 e docs/explanation/domains/scheduling-domain.md.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def buscar_atendimento(
        self,
        atendimento_id: UUID,
    ) -> AtendimentoSnapshotDTO | None:
        """Busca snapshot imutável do atendimento diretamente na tabela atendimentos.

        Regras: ADR-001 e docs/explanation/domains/scheduling-domain.md.
        """
        stmt = (
            select(
                Atendimento.id,
                Atendimento.paciente_id,
                Atendimento.medico_id,
                Atendimento.status,
                Atendimento.prioridade_clinica,
                Atendimento.tcle_hash,
                Atendimento.data_entrada_fila,
                Atendimento.criado_em,
                Atendimento.chamada_iniciada_em,
            )
            .where(Atendimento.id == atendimento_id)
            .limit(1)
        )
        row = (await self._session.execute(stmt)).mappings().one_or_none()
        if row is None:
            return None
        status_val = str(row["status"])
        return AtendimentoSnapshotDTO(
            id=row["id"],
            paciente_id=row["paciente_id"],
            medico_id=row["medico_id"],
            status=status_val,
            prioridade_clinica=int(row["prioridade_clinica"]),
            tcle_hash=row["tcle_hash"],
            data_entrada_fila=row["data_entrada_fila"],
            criado_em=row["criado_em"],
            is_terminal=status_val in TERMINAL_STATUSES,
            chamada_iniciada_em=row["chamada_iniciada_em"],
        )
