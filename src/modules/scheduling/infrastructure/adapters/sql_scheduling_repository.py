"""Adaptador SQLAlchemy 2.0 assíncrono para SchedulingRepositoryPort."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.scheduling.application.ports.scheduling_repository_port import (
    SchedulingRepositoryPort,
)
from src.modules.scheduling.domain.models import (
    STATUS_AGENDAMENTO_INATIVOS,
    AgendaDisponibilidade,
    Agendamento,
)

_STATUS_INATIVOS_STR: tuple[str, ...] = tuple(
    s.value for s in STATUS_AGENDAMENTO_INATIVOS
)


class SqlSchedulingRepository(SchedulingRepositoryPort):
    """Repositório relacional de disponibilidades e agendamentos multiprofissionais."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def listar_disponibilidades_ativas(
        self,
        organizacao_id: int,
        especialidade: str,
    ) -> Sequence[AgendaDisponibilidade]:
        stmt = (
            select(AgendaDisponibilidade)
            .where(
                AgendaDisponibilidade.organizacao_id == organizacao_id,
                AgendaDisponibilidade.especialidade == especialidade,
                AgendaDisponibilidade.ativo.is_(True),
            )
            .order_by(
                AgendaDisponibilidade.dia_semana, AgendaDisponibilidade.hora_inicio
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def listar_agendamentos_ocupados(
        self,
        organizacao_id: int,
        inicio: datetime,
        fim: datetime,
    ) -> Sequence[Agendamento]:
        stmt = select(Agendamento).where(
            Agendamento.organizacao_id == organizacao_id,
            Agendamento.status.notin_(_STATUS_INATIVOS_STR),
            Agendamento.slot_inicio < fim,
            Agendamento.slot_fim > inicio,
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def buscar_agendamento_conflitante(
        self,
        organizacao_id: int,
        profissional_id: UUID,
        slot_inicio: datetime,
        slot_fim: datetime,
    ) -> Agendamento | None:
        stmt = (
            select(Agendamento)
            .where(
                Agendamento.organizacao_id == organizacao_id,
                Agendamento.profissional_id == profissional_id,
                Agendamento.status.notin_(_STATUS_INATIVOS_STR),
                Agendamento.slot_inicio < slot_fim,
                Agendamento.slot_fim > slot_inicio,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def buscar_disponibilidade_profissional(
        self,
        organizacao_id: int,
        profissional_id: UUID,
        especialidade: str | None,
        dia_semana: int,
    ) -> Sequence[AgendaDisponibilidade]:
        stmt = select(AgendaDisponibilidade).where(
            AgendaDisponibilidade.organizacao_id == organizacao_id,
            AgendaDisponibilidade.profissional_id == profissional_id,
            AgendaDisponibilidade.dia_semana == dia_semana,
            AgendaDisponibilidade.ativo.is_(True),
        )
        if especialidade is not None:
            stmt = stmt.where(AgendaDisponibilidade.especialidade == especialidade)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def buscar_agendamento_por_id(
        self,
        organizacao_id: int,
        agendamento_id: UUID,
        for_update: bool = False,
    ) -> Agendamento | None:
        stmt = select(Agendamento).where(
            Agendamento.organizacao_id == organizacao_id,
            Agendamento.id == agendamento_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def listar_agendamentos_paciente(
        self,
        organizacao_id: int,
        paciente_id: UUID,
    ) -> Sequence[Agendamento]:
        stmt = (
            select(Agendamento)
            .where(
                Agendamento.organizacao_id == organizacao_id,
                Agendamento.paciente_id == paciente_id,
            )
            .order_by(Agendamento.slot_inicio.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def listar_agendamentos_profissional(
        self,
        organizacao_id: int,
        profissional_id: UUID,
        inicio: datetime,
        fim: datetime,
    ) -> Sequence[Agendamento]:
        stmt = (
            select(Agendamento)
            .where(
                Agendamento.organizacao_id == organizacao_id,
                Agendamento.profissional_id == profissional_id,
                Agendamento.slot_inicio >= inicio,
                Agendamento.slot_inicio < fim,
            )
            .order_by(Agendamento.slot_inicio.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    def adicionar_disponibilidade(self, disponibilidade: AgendaDisponibilidade) -> None:
        self._session.add(disponibilidade)

    def adicionar_agendamento(self, agendamento: Agendamento) -> None:
        self._session.add(agendamento)
