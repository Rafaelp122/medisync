"""Facial liveness verification adapter for US-15."""

import hashlib
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from redis.asyncio import Redis

from src.core.uuid7 import uuid7
from src.modules.consultation.application.ports.liveness_verification_port import (
    LivenessChallengeDTO,
    LivenessVerificationPort,
    LivenessVerificationResultDTO,
)

_SPOOF_MARKERS = ("SPOOF", "STATIC_PHOTO", "DEEPFAKE", "REPLAY")
_DEFAULT_INSTRUCTIONS = ["piscar_olhos", "sorrir"]
_CHALLENGE_TTL_SECONDS = 60
_APPROVED_HASH_TTL_SECONDS = 3600


def _decode_redis_str(raw: object) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)


def _build_liveness_hash(
    provider_name: str, atendimento_id: UUID, challenge_id: str, payload: str
) -> str:
    digest = hashlib.sha256(
        f"{provider_name}:{atendimento_id}:{challenge_id}:{payload}".encode()
    ).hexdigest()
    return f"sha256_{digest}"


def _evaluate_liveness_payload(
    *,
    provider_name: str,
    atendimento_id: UUID,
    challenge_id: str,
    liveness_payload: str,
) -> tuple[LivenessVerificationResultDTO, bool]:
    cleaned = liveness_payload.strip()
    verificacao_hash = _build_liveness_hash(
        provider_name, atendimento_id, challenge_id, cleaned
    )
    upper_payload = cleaned.upper()
    is_spoof = (not cleaned) or any(
        marker in upper_payload for marker in _SPOOF_MARKERS
    )
    if is_spoof:
        return (
            LivenessVerificationResultDTO(
                status="REPROVADO",
                liveness_score=0.42,
                verificacao_hash=verificacao_hash,
                validado_em=datetime.now(UTC),
            ),
            False,
        )
    return (
        LivenessVerificationResultDTO(
            status="APROVADO",
            liveness_score=0.98,
            verificacao_hash=verificacao_hash,
            validado_em=datetime.now(UTC),
        ),
        True,
    )


class MockLivenessAdapter(LivenessVerificationPort):
    """Adaptador em memória para testes unitários isolados de prova de vida (US-15).

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
            timeout_segundos=_CHALLENGE_TTL_SECONDS,
        )

    async def verificar_prova_de_vida(
        self,
        atendimento_id: UUID,
        challenge_id: str,
        liveness_payload: str,
    ) -> LivenessVerificationResultDTO:
        """Avalia frames de vivacidade validando vínculo single-use do challenge_id.

        Regras: RF-07, LGPD Art. 11 e
        docs/user-stories/US-15-prova-de-vida-facial-liveness.md.
        """
        bound_atendimento = self._challenges.pop(challenge_id, None)
        if bound_atendimento != atendimento_id:
            self._approved_hashes.pop(atendimento_id, None)
            return LivenessVerificationResultDTO(
                status="DESAFIO_INVALIDO",
                liveness_score=0.0,
                verificacao_hash=_build_liveness_hash(
                    self.provider_name,
                    atendimento_id,
                    challenge_id,
                    liveness_payload.strip(),
                ),
                validado_em=datetime.now(UTC),
            )

        result, approved = _evaluate_liveness_payload(
            provider_name=self.provider_name,
            atendimento_id=atendimento_id,
            challenge_id=challenge_id,
            liveness_payload=liveness_payload,
        )
        if approved:
            self._approved_hashes[atendimento_id] = result.verificacao_hash
        else:
            self._approved_hashes.pop(atendimento_id, None)
        return result

    async def obter_hash_aprovado(self, atendimento_id: UUID) -> str | None:
        """Retorna hash SHA-256 de prova de vida aprovada para o atendimento.

        Regras: RF-07 e docs/user-stories/US-15-prova-de-vida-facial-liveness.md.
        """
        return self._approved_hashes.get(atendimento_id)


class ValkeyLivenessAdapter(LivenessVerificationPort):
    """Adaptador distribuído em Valkey para prova de vida facial (US-15).

    Persiste desafios single-use com consumo atômico via ``GETDEL`` (TTL 60s)
    e registra o hash aprovado por atendimento com TTL de 3600s.
    Regras: RF-07, Portaria 344/98 Lista C1/C5 e LGPD Art. 11.
    Documentação: docs/user-stories/US-15-prova-de-vida-facial-liveness.md
    """

    provider_name: ClassVar[str] = "valkey_sandbox_liveness"

    def __init__(self, valkey: Redis) -> None:
        self._valkey = valkey

    @staticmethod
    def _challenge_key(challenge_id: str) -> str:
        return f"liveness:challenge:{challenge_id}"

    @staticmethod
    def _approved_key(atendimento_id: UUID) -> str:
        return f"liveness:approved:{atendimento_id}"

    async def gerar_desafio(self, atendimento_id: UUID) -> LivenessChallengeDTO:
        """Gera desafio single-use persistido em Valkey com expiração de 60s.

        Regras: RF-07 e docs/user-stories/US-15-prova-de-vida-facial-liveness.md.
        """
        challenge_id = f"ch_{uuid7().hex[:12]}"
        await self._valkey.set(  # pyright: ignore[reportUnknownMemberType]
            self._challenge_key(challenge_id),
            str(atendimento_id),
            ex=_CHALLENGE_TTL_SECONDS,
        )
        return LivenessChallengeDTO(
            challenge_id=challenge_id,
            instrucoes_movimento=list(_DEFAULT_INSTRUCTIONS),
            timeout_segundos=_CHALLENGE_TTL_SECONDS,
        )

    async def verificar_prova_de_vida(
        self,
        atendimento_id: UUID,
        challenge_id: str,
        liveness_payload: str,
    ) -> LivenessVerificationResultDTO:
        """Consome desafio atomicamente em Valkey via GETDEL e valida vivacidade.

        Regras: RF-07, LGPD Art. 11 e
        docs/user-stories/US-15-prova-de-vida-facial-liveness.md.
        """
        raw_bound = await self._valkey.getdel(  # pyright: ignore[reportUnknownMemberType]
            self._challenge_key(challenge_id)
        )
        bound_atendimento = _decode_redis_str(raw_bound)
        if bound_atendimento != str(atendimento_id):
            await self._valkey.delete(self._approved_key(atendimento_id))  # pyright: ignore[reportUnknownMemberType]
            return LivenessVerificationResultDTO(
                status="DESAFIO_INVALIDO",
                liveness_score=0.0,
                verificacao_hash=_build_liveness_hash(
                    self.provider_name,
                    atendimento_id,
                    challenge_id,
                    liveness_payload.strip(),
                ),
                validado_em=datetime.now(UTC),
            )

        result, approved = _evaluate_liveness_payload(
            provider_name=self.provider_name,
            atendimento_id=atendimento_id,
            challenge_id=challenge_id,
            liveness_payload=liveness_payload,
        )
        approved_key = self._approved_key(atendimento_id)
        if approved:
            await self._valkey.set(  # pyright: ignore[reportUnknownMemberType]
                approved_key,
                result.verificacao_hash,
                ex=_APPROVED_HASH_TTL_SECONDS,
            )
        else:
            await self._valkey.delete(approved_key)  # pyright: ignore[reportUnknownMemberType]
        return result

    async def obter_hash_aprovado(self, atendimento_id: UUID) -> str | None:
        """Retorna hash SHA-256 aprovado no Valkey para o atendimento ativo.

        Regras: RF-07 e docs/user-stories/US-15-prova-de-vida-facial-liveness.md.
        """
        raw = await self._valkey.get(self._approved_key(atendimento_id))  # pyright: ignore[reportUnknownMemberType]
        return _decode_redis_str(raw)
