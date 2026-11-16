"""Abstract port for facial liveness detection on controlled prescriptions."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True)
class LivenessChallengeDTO:
    """Challenge instructions dispatched to verify patient physical presence."""

    challenge_id: str
    instrucoes_movimento: list[str]
    timeout_segundos: int = 60


@dataclass(frozen=True)
class LivenessVerificationResultDTO:
    """Biometric liveness verification result with SHA-256 audit hash."""

    status: str
    liveness_score: float
    verificacao_hash: str
    validado_em: datetime


@runtime_checkable
class LivenessVerificationPort(Protocol):
    """Protocol for active facial liveness detection providers (Gov.br/Datavalid)."""

    async def gerar_desafio(self, atendimento_id: UUID) -> LivenessChallengeDTO:
        """Issue a liveness challenge with movement prompts for the attendance."""
        ...

    async def verificar_prova_de_vida(
        self,
        atendimento_id: UUID,
        challenge_id: str,
        liveness_payload: str,
    ) -> LivenessVerificationResultDTO:
        """Analyze liveness frames and return score plus SHA-256 verification hash."""
        ...

    async def obter_hash_aprovado(self, atendimento_id: UUID) -> str | None:
        """Return previously approved SHA-256 liveness hash for the attendance."""
        ...
