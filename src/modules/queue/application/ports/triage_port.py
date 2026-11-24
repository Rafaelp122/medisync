"""Unified port and DTO for delegating clinical triage across queue and triage."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID


class TriageEvaluationDTO(Protocol):
    """Protocol for clinical risk evaluation outcome from triage domain."""

    @property
    def prioridade_clinica(self) -> int: ...

    @property
    def tcle_hash(self) -> str: ...

    @property
    def alerta_samu_disparado(self) -> bool: ...

    @property
    def instrucao_redirecionamento(self) -> str | None: ...


@runtime_checkable
class TriagePort(Protocol):
    """Seam único entre queue e triage: risco, persistência 1:1 e leitura de queixas."""

    async def avaliar_risco(
        self,
        queixa_principal: str,
        sintomas: Sequence[str],
        escala_dor: int = 0,
        tcle_texto: str = "",
        tcle_hash: str | None = None,
        *,
        raise_on_emergency: bool = True,
        atendimento_id: UUID | None = None,
    ) -> TriageEvaluationDTO:
        """Classify clinical risk and trigger SAMU 192 alert if level 1."""
        ...

    async def registrar_triagem(
        self,
        atendimento_id: UUID,
        queixa_principal: str,
        sintomas: Sequence[str],
        prioridade_calculada: int | None = None,
        alerta_samu_disparado: bool = False,
        escala_dor: int = 0,
    ) -> UUID:
        """Persist Triagem aggregate associated 1:1 with attendance."""
        ...

    async def obter_queixas_por_atendimentos(
        self,
        atendimento_ids: Sequence[UUID],
    ) -> dict[UUID, str | None]:
        """Fetch mapping atendimento_id -> queixa_principal by attendance IDs."""
        ...
