"""Porta abstrata (PEP 544) para consulta cross-module de atendimentos clínicos."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class AttendanceSnapshot:
    """Projeção imutável do atendimento clínico para vínculo seguro ao agendamento."""

    id: UUID
    paciente_id: UUID
    medico_id: UUID | None


class AttendanceLookupPort(Protocol):
    """Contrato estrutural para validar existência e titularidade de atendimento."""

    async def buscar_atendimento(
        self,
        atendimento_id: UUID,
    ) -> AttendanceSnapshot | None: ...
