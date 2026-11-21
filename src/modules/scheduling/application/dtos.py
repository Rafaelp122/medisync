"""Commands e DTOs de aplicação do módulo scheduling."""

from dataclasses import dataclass
from datetime import datetime, time
from uuid import UUID


@dataclass(frozen=True)
class SlotDisponivelDTO:
    """Slot livre gerado a partir das janelas de disponibilidade ativas."""

    profissional_id: UUID
    especialidade: str
    slot_inicio: datetime
    slot_fim: datetime
    duracao_minutos: int


@dataclass(frozen=True)
class CriarDisponibilidadeCommand:
    """Command para cadastro de janela semanal de disponibilidade."""

    profissional_id: UUID
    especialidade: str
    dia_semana: int
    hora_inicio: time
    hora_fim: time
    duracao_minutos: int


@dataclass(frozen=True)
class AgendarConsultaCommand:
    """Command para agendamento de consulta pelo paciente autenticado."""

    paciente_id: UUID
    profissional_id: UUID
    especialidade: str
    slot_inicio: datetime
    slot_fim: datetime | None = None
    observacoes: str | None = None
