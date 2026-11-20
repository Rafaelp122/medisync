"""Porta abstrata (PEP 544) para persistência do módulo scheduling."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.modules.scheduling.domain.models import AgendaDisponibilidade, Agendamento


class SchedulingRepositoryPort(Protocol):
    """Contrato estrutural de acesso a disponibilidades e agendamentos."""

    async def listar_disponibilidades_ativas(
        self,
        especialidade: str,
    ) -> Sequence[AgendaDisponibilidade]: ...

    async def listar_agendamentos_ocupados(
        self,
        inicio: datetime,
        fim: datetime,
    ) -> Sequence[Agendamento]: ...

    async def buscar_agendamento_conflitante(
        self,
        profissional_id: UUID,
        slot_inicio: datetime,
        slot_fim: datetime,
    ) -> Agendamento | None: ...

    async def buscar_disponibilidade_profissional(
        self,
        profissional_id: UUID,
        especialidade: str | None,
        dia_semana: int,
    ) -> Sequence[AgendaDisponibilidade]: ...

    async def buscar_agendamento_por_id(
        self,
        agendamento_id: UUID,
        for_update: bool = False,
    ) -> Agendamento | None: ...

    async def listar_agendamentos_paciente(
        self,
        paciente_id: UUID,
    ) -> Sequence[Agendamento]: ...

    async def listar_agendamentos_profissional(
        self,
        profissional_id: UUID,
        inicio: datetime,
        fim: datetime,
    ) -> Sequence[Agendamento]: ...

    def adicionar_disponibilidade(
        self, disponibilidade: AgendaDisponibilidade
    ) -> None: ...

    def adicionar_agendamento(self, agendamento: Agendamento) -> None: ...
