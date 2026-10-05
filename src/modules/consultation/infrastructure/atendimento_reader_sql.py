"""SQL reader: single SELECT on atendimentos (queue-owned table)."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoResumoDTO,
)

_TERMINAIS = frozenset({"CONCLUIDO", "PACIENTE_AUSENTE", "CANCELADO_PACIENTE"})


class SqlAtendimentoReader:
    """Concentrates all cross-module reads of the queue-owned atendimentos table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def obter_resumo(self, atendimento_id: UUID) -> AtendimentoResumoDTO | None:
        res = await self._session.execute(
            text(
                "SELECT id, organizacao_id, medico_id, status, tcle_hash "
                "FROM atendimentos WHERE id = :id"
            ),
            {"id": atendimento_id},
        )
        row = res.mappings().one_or_none()
        if row is None:
            return None
        status = str(row["status"]).strip().upper()
        raw_med = row["medico_id"]
        return AtendimentoResumoDTO(
            atendimento_id=row["id"],
            organizacao_id=int(row["organizacao_id"]),
            medico_id=raw_med
            if isinstance(raw_med, UUID) or raw_med is None
            else UUID(str(raw_med)),
            status=status,
            tcle_hash=row["tcle_hash"],
            is_terminal=status in _TERMINAIS,
        )
