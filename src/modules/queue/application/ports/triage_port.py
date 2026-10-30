"""Port and DTO for delegating triage and clinical risk classification (NC-ARQ-01)."""

from typing import Protocol
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


class TriagePort(Protocol):
    """Abstract port for clinical risk evaluation and triage persistence."""

    async def avaliar_risco(
        self,
        organizacao_id: int,
        queixa_principal: str,
        sintomas: list[str],
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
        organizacao_id: int,
        atendimento_id: UUID,
        queixa_principal: str,
        sintomas: list[str],
        prioridade_calculada: int,
        alerta_samu_disparado: bool = False,
        escala_dor: int = 0,
    ) -> UUID:
        """Persist Triagem aggregate associated 1:1 with attendance."""
        ...
