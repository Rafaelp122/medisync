"""Facial liveness verification adapters (Mock, Gov.br, Datavalid) for US-15."""

import hashlib
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from src.core.uuid7 import uuid7
from src.modules.consultation.application.ports.liveness_verification_port import (
    LivenessChallengeDTO,
    LivenessVerificationPort,
    LivenessVerificationResultDTO,
)

_SPOOF_MARKERS = ("SPOOF", "STATIC_PHOTO", "DEEPFAKE", "REPLAY")
_DEFAULT_INSTRUCTIONS = ["piscar_olhos", "sorrir"]


class MockLivenessAdapter(LivenessVerificationPort):
    """Adaptador em memória / sandbox para prova de vida facial (Liveness US-15).

    Regras: RF-07, Portaria 344/98 Lista C1 e LGPD Art. 11.
    Documentação: docs/user-stories/US-15-prova-de-vida-facial-liveness.md
    """

    _shared_challenges: ClassVar[dict[str, UUID]] = {}
    _shared_approved_hashes: ClassVar[dict[UUID, str]] = {}
    provider_name: ClassVar[str] = "mock_liveness"

    def __init__(self, *, isolated: bool = False) -> None:
        self._challenges: dict[str, UUID] = (
            {} if isolated else MockLivenessAdapter._shared_challenges
        )
        self._approved_hashes: dict[UUID, str] = (
            {} if isolated else MockLivenessAdapter._shared_approved_hashes
        )

    @classmethod
    def reset(cls) -> None:
        """Clear shared in-memory liveness state across isolated test runs."""
        cls._shared_challenges.clear()
        cls._shared_approved_hashes.clear()

    async def gerar_desafio(self, atendimento_id: UUID) -> LivenessChallengeDTO:
        """Gera desafio de movimentação facial para comprovação ativa de vivacidade.

        Regras: RF-07 e docs/user-stories/US-15-prova-de-vida-facial-liveness.md.
        """
        challenge_id = f"ch_{uuid7().hex[:12]}"
        self._challenges[challenge_id] = atendimento_id
        return LivenessChallengeDTO(
            challenge_id=challenge_id,
            instrucoes_movimento=list(_DEFAULT_INSTRUCTIONS),
            timeout_segundos=60,
        )

    async def verificar_prova_de_vida(
        self,
        atendimento_id: UUID,
        challenge_id: str,
        liveness_payload: str,
    ) -> LivenessVerificationResultDTO:
        """Avalia frames de vivacidade detectando tentativas de spoofing facial.

        Regras: RF-07, LGPD Art. 11 e
        docs/user-stories/US-15-prova-de-vida-facial-liveness.md.
        """
        cleaned = liveness_payload.strip()
        upper_payload = cleaned.upper()
        digest = hashlib.sha256(
            f"{self.provider_name}:{atendimento_id}:{challenge_id}:{cleaned}".encode()
        ).hexdigest()
        verificacao_hash = f"sha256_{digest}"

        is_spoof = (not cleaned) or any(
            marker in upper_payload for marker in _SPOOF_MARKERS
        )
        if is_spoof:
            self._approved_hashes.pop(atendimento_id, None)
            return LivenessVerificationResultDTO(
                status="REPROVADO",
                liveness_score=0.42,
                verificacao_hash=verificacao_hash,
                validado_em=datetime.now(UTC),
            )

        self._approved_hashes[atendimento_id] = verificacao_hash
        return LivenessVerificationResultDTO(
            status="APROVADO",
            liveness_score=0.98,
            verificacao_hash=verificacao_hash,
            validado_em=datetime.now(UTC),
        )

    async def obter_hash_aprovado(self, atendimento_id: UUID) -> str | None:
        """Retorna hash SHA-256 de prova de vida aprovada para o atendimento.

        Regras: RF-07 e docs/user-stories/US-15-prova-de-vida-facial-liveness.md.
        """
        return self._approved_hashes.get(atendimento_id)


class GovBrLivenessAdapter(MockLivenessAdapter):
    """Adaptador de prova de vida facial compatível com Gov.br (sandbox local).

    Regras: RF-07 e docs/user-stories/US-15-prova-de-vida-facial-liveness.md.
    """

    provider_name: ClassVar[str] = "govbr"


class DatavalidLivenessAdapter(MockLivenessAdapter):
    """Adaptador de prova de vida facial compatível com Serpro Datavalid (sandbox).

    Regras: RF-07 e docs/user-stories/US-15-prova-de-vida-facial-liveness.md.
    """

    provider_name: ClassVar[str] = "datavalid"
