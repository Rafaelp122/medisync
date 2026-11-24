"""SQL reader: single SELECT on atendimentos (queue-owned table)."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoHistoricoDTO,
    AtendimentoResumoDTO,
)

_TERMINAIS = frozenset({"CONCLUIDO", "PACIENTE_AUSENTE", "CANCELADO_PACIENTE"})


def _parse_optional_uuid(raw: Any) -> UUID | None:
    if raw is None or isinstance(raw, UUID):
        return raw
    return UUID(str(raw))


def _row_to_historico_dto(row: Mapping[Any, Any]) -> AtendimentoHistoricoDTO:
    raw_atend = row["atendimento_id"]
    raw_pac = row["paciente_id"]
    atend_id = raw_atend if isinstance(raw_atend, UUID) else UUID(str(raw_atend))
    return AtendimentoHistoricoDTO(
        atendimento_id=atend_id,
        paciente_id=raw_pac if isinstance(raw_pac, UUID) else UUID(str(raw_pac)),
        status=str(row["status"]).strip().upper(),
        prioridade_clinica=int(row["prioridade_clinica"]),
        criado_em=row["criado_em"],
        finalizado_em=row.get("finalizado_em"),
        medico_id=_parse_optional_uuid(row.get("medico_id")),
        queixa_principal=row.get("queixa_principal"),
    )


class SqlAtendimentoReader:
    """Concentrates all cross-module reads of the queue-owned atendimentos table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def obter_resumo(self, atendimento_id: UUID) -> AtendimentoResumoDTO | None:
        res = await self._session.execute(
            text(
                "SELECT id, paciente_id, medico_id, status, tcle_hash, "
                "chamada_iniciada_em, criado_em "
                "FROM atendimentos WHERE id = :id"
            ),
            {"id": atendimento_id},
        )
        row = res.mappings().one_or_none()
        if row is None:
            return None
        status = str(row["status"]).strip().upper()
        raw_med = row["medico_id"]
        raw_pac = row.get("paciente_id")
        return AtendimentoResumoDTO(
            atendimento_id=row["id"],
            medico_id=raw_med
            if isinstance(raw_med, UUID) or raw_med is None
            else UUID(str(raw_med)),
            status=status,
            tcle_hash=row["tcle_hash"],
            is_terminal=status in _TERMINAIS,
            paciente_id=raw_pac
            if isinstance(raw_pac, UUID) or raw_pac is None
            else UUID(str(raw_pac)),
            chamada_iniciada_em=row.get("chamada_iniciada_em"),
            criado_em=row.get("criado_em"),
        )

    async def concluir_atendimento(
        self,
        atendimento_id: UUID,
        *,
        auto_commit: bool = True,
    ) -> UUID | None:
        await self._session.execute(
            text(
                "UPDATE atendimentos SET status = 'CONCLUIDO', "
                "chamada_finalizada_em = NOW(), atualizado_em = NOW() "
                "WHERE id = :id"
            ),
            {"id": atendimento_id},
        )
        if auto_commit:
            await self._session.commit()
        else:
            await self._session.flush()
        return None

    async def liberar_consulta_ativa_medico(self, medico_id: UUID) -> None:
        """No-op fallback when SQL reader runs without Valkey queue engine."""
        return None

    async def atender_chamada(self, atendimento_id: UUID) -> None:
        await self._session.execute(
            text(
                "UPDATE atendimentos SET status = 'EM_ATENDIMENTO', "
                "atualizado_em = NOW() "
                "WHERE id = :id AND status = 'CHAMANDO_PACIENTE'"
            ),
            {"id": atendimento_id},
        )
        await self._session.commit()

    async def listar_historico_paciente(
        self,
        paciente_id: UUID,
    ) -> list[AtendimentoHistoricoDTO]:
        res = await self._session.execute(
            text(
                "SELECT id AS atendimento_id, paciente_id, "
                "status, prioridade_clinica, criado_em, "
                "chamada_finalizada_em AS finalizado_em, medico_id "
                "FROM atendimentos "
                "WHERE paciente_id = :paciente_id "
                "ORDER BY criado_em DESC, id DESC"
            ),
            {"paciente_id": paciente_id},
        )
        rows = res.mappings().all()
        return [_row_to_historico_dto(row) for row in rows]
