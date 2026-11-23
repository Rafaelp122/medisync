"""Deep Valkey infrastructure engine implementing QueueEnginePort (ADR-002)."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from redis.asyncio import Redis

from src.core.realtime import publish_realtime_event
from src.modules.queue.application.ports.allocation_port import AlocacaoCodigo
from src.modules.queue.application.ports.queue_engine_port import QueueEnginePort
from src.modules.queue.application.realtime_channels import channel_queue_patient
from src.modules.queue.infrastructure.lua_loader import (
    LuaScriptManager,
    get_lua_script_manager,
)

FILA_APTOS_KEY = "fila:aptos"
PLANTAO_MEDICOS_KEY = "plantao:medicos_ativos"
SWEEPER_LOCK_KEY = "lock:sweeper:fila_aptos"
_LOCK_ATENDIMENTO_PREFIX = "lock:atendimento:"
_COTA_TTL_SEGUNDOS = 86400 * 2
_LOCK_CONSULTA_TTL_SEGUNDOS = 7200


def _default_doctor_channel(medico_id: UUID) -> str:
    return f"medisync:pubsub:doctor:{medico_id}"


def _lock_matches(raw: object, expected: str) -> bool:
    if raw is None:
        return False
    decoded = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    return decoded == expected


class ValkeyQueueEngine(QueueEnginePort):
    """Concrete Valkey/Lua engine encapsulating keys, locks, quotas, and Pub/Sub.

    Regras: ADR-002 e docs/reference/valkey/keys-dictionary.md
    """

    def __init__(
        self,
        valkey: Redis,
        lua_manager: LuaScriptManager | None = None,
        *,
        doctor_channel_fn: Callable[[UUID], str] | None = None,
    ) -> None:
        self._valkey = valkey
        self._lua_manager = lua_manager or get_lua_script_manager()
        self._doctor_channel_fn = doctor_channel_fn or _default_doctor_channel

    @staticmethod
    def _k_lock_medico(medico_id: UUID) -> str:
        return f"lock:medico:{medico_id}"

    @staticmethod
    def _k_lock_atendimento(atendimento_id: UUID) -> str:
        return f"{_LOCK_ATENDIMENTO_PREFIX}{atendimento_id}"

    @staticmethod
    def _k_lock_consulta_ativa(medico_id: UUID) -> str:
        return f"lock:consulta_ativa:medico:{medico_id}"

    @staticmethod
    def _k_cota_diaria() -> str:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        return f"queue:admissoes:{today}"

    async def alocar_proximo(
        self,
        medico_id: UUID,
        ttl_segundos: int = 45,
        max_scan: int = 50,
    ) -> tuple[AlocacaoCodigo, UUID | None]:
        """Atomically select and lock the first unlocked candidate from fila:aptos."""
        keys = [
            self._k_lock_medico(medico_id),
            _LOCK_ATENDIMENTO_PREFIX,
            FILA_APTOS_KEY,
            self._k_lock_consulta_ativa(medico_id),
        ]
        args: list[object] = [str(medico_id), int(ttl_segundos), int(max_scan)]
        return await self._lua_manager.alocar_proximo(self._valkey, keys, args)

    async def alocar_atendimento(
        self,
        medico_id: UUID,
        atendimento_id: UUID,
        ttl_segundos: int = 45,
    ) -> AlocacaoCodigo:
        """Atomically allocate a specific attendance using 4-Keys Lua validation."""
        keys = [
            self._k_lock_medico(medico_id),
            self._k_lock_atendimento(atendimento_id),
            FILA_APTOS_KEY,
            self._k_lock_consulta_ativa(medico_id),
        ]
        args: list[object] = [str(medico_id), str(atendimento_id), int(ttl_segundos)]
        return await self._lua_manager.alocar_chamada(self._valkey, keys, args)

    async def promover_para_consulta(
        self,
        medico_id: UUID,
        atendimento_id: UUID,
        ttl_segundos: int = _LOCK_CONSULTA_TTL_SEGUNDOS,
    ) -> None:
        """Promote ring lock into active consultation lock and clear ring keys."""
        async with self._valkey.pipeline(transaction=True) as pipe:
            pipe.delete(self._k_lock_atendimento(atendimento_id))
            pipe.delete(self._k_lock_medico(medico_id))
            pipe.set(
                self._k_lock_consulta_ativa(medico_id),
                str(atendimento_id),
                ex=ttl_segundos,
            )
            await pipe.execute()

    async def liberar_ring(
        self,
        medico_id: UUID,
        atendimento_id: UUID,
    ) -> None:
        """Delete transient doctor and attendance ring locks in one pipeline."""
        async with self._valkey.pipeline(transaction=True) as pipe:
            pipe.delete(self._k_lock_medico(medico_id))
            pipe.delete(self._k_lock_atendimento(atendimento_id))
            await pipe.execute()

    async def liberar_consulta(self, medico_id: UUID) -> None:
        """Delete active consultation lock held by the doctor."""
        await self._valkey.delete(self._k_lock_consulta_ativa(medico_id))

    async def devolver_para_fila(
        self,
        atendimento_id: UUID,
        score: int,
        medico_id: UUID | None = None,
        *,
        nx: bool = False,
    ) -> bool:
        """Clear ring locks and reinject attendance into fila:aptos in one pipeline."""
        async with self._valkey.pipeline(transaction=True) as pipe:
            pipe.delete(self._k_lock_atendimento(atendimento_id))
            if medico_id is not None:
                pipe.delete(self._k_lock_medico(medico_id))
            pipe.zadd(FILA_APTOS_KEY, {str(atendimento_id): score}, nx=nx)  # pyright: ignore[reportUnknownMemberType]
            results = await pipe.execute()
        return bool(results[-1]) if results else False

    async def inserir_ou_atualizar_fila(
        self,
        atendimento_id: UUID,
        score: int,
        *,
        nx: bool = False,
    ) -> int | None:
        """Insert or update member score in fila:aptos and return 0-based rank."""
        atend_str = str(atendimento_id)
        async with self._valkey.pipeline(transaction=True) as pipe:
            pipe.zadd(FILA_APTOS_KEY, {atend_str: score}, nx=nx)  # pyright: ignore[reportUnknownMemberType]
            pipe.zrank(FILA_APTOS_KEY, atend_str)  # pyright: ignore[reportUnknownMemberType]
            results = await pipe.execute()
        raw_rank = results[-1] if results else None
        return int(raw_rank) if raw_rank is not None else None

    async def remover_da_fila(self, atendimento_id: UUID) -> bool:
        """Remove attendance from fila:aptos sorted set."""
        removed = await cast(
            "Awaitable[int]",
            self._valkey.zrem(FILA_APTOS_KEY, str(atendimento_id)),  # pyright: ignore[reportUnknownMemberType]
        )
        return int(removed) > 0

    async def obter_posicao_e_tamanho(
        self,
        atendimento_id: UUID,
    ) -> tuple[int | None, int]:
        """Fetch 0-based ZRANK and total ZCARD in a single pipeline round-trip."""
        async with self._valkey.pipeline(transaction=True) as pipe:
            pipe.zrank(FILA_APTOS_KEY, str(atendimento_id))  # pyright: ignore[reportUnknownMemberType]
            pipe.zcard(FILA_APTOS_KEY)  # pyright: ignore[reportUnknownMemberType]
            results = await pipe.execute()
        raw_rank = results[0]
        rank = int(raw_rank) if raw_rank is not None else None
        total = int(results[1] or 0)
        return rank, total

    async def obter_tamanho_fila(self) -> int:
        """Return total number of waiting attendances in fila:aptos."""
        card = await cast("Awaitable[int]", self._valkey.zcard(FILA_APTOS_KEY))  # pyright: ignore[reportUnknownMemberType]
        return int(card)

    async def consumir_cota_ou_bloquear(
        self,
        cota_diaria_maxima: int | None,
    ) -> tuple[bool, int]:
        """Atomically increment daily counter and roll back via DECR if cap exceeded."""
        k_cota = self._k_cota_diaria()
        val = int(await cast("Awaitable[int]", self._valkey.incr(k_cota)))  # pyright: ignore[reportUnknownMemberType]
        await cast("Awaitable[bool]", self._valkey.expire(k_cota, _COTA_TTL_SEGUNDOS))  # pyright: ignore[reportUnknownMemberType]
        if cota_diaria_maxima is not None and val > cota_diaria_maxima:
            restored = int(await cast("Awaitable[int]", self._valkey.decr(k_cota)))  # pyright: ignore[reportUnknownMemberType]
            return False, max(0, restored)
        return True, val

    async def estornar_cota_diaria(self) -> None:
        """Decrement daily admission counter on failure before/during DB commit."""
        k_cota = self._k_cota_diaria()
        val = int(await cast("Awaitable[int]", self._valkey.decr(k_cota)))  # pyright: ignore[reportUnknownMemberType]
        if val < 0:
            await self._valkey.set(k_cota, 0, ex=_COTA_TTL_SEGUNDOS)

    async def registrar_medico_ativo(self, medico_id: UUID) -> None:
        """Idempotently add doctor ID to active shift presence SET."""
        await cast(
            "Awaitable[int]",
            self._valkey.sadd(PLANTAO_MEDICOS_KEY, str(medico_id)),  # pyright: ignore[reportUnknownMemberType]
        )

    async def desregistrar_medico_ativo(self, medico_id: UUID) -> None:
        """Remove doctor ID from active shift presence SET."""
        await cast(
            "Awaitable[int]",
            self._valkey.srem(PLANTAO_MEDICOS_KEY, str(medico_id)),  # pyright: ignore[reportUnknownMemberType]
        )

    async def obter_medicos_ativos_count(self) -> int:
        """Count distinct active doctors in plantao:medicos_ativos."""
        count = await cast("Awaitable[int]", self._valkey.scard(PLANTAO_MEDICOS_KEY))  # pyright: ignore[reportUnknownMemberType]
        return int(count)

    async def publicar_evento_fila(
        self,
        atendimento_id: UUID,
        payload: dict[str, object],
    ) -> None:
        """Publish realtime event on patient waiting room Pub/Sub channel."""
        await publish_realtime_event(
            valkey=self._valkey,
            channel=channel_queue_patient(atendimento_id),
            payload=cast("dict[str, Any]", dict(payload)),
        )

    async def publicar_evento_medico(
        self,
        medico_id: UUID,
        payload: dict[str, object],
    ) -> None:
        """Publish realtime event on doctor call lifecycle Pub/Sub channel."""
        await publish_realtime_event(
            valkey=self._valkey,
            channel=self._doctor_channel_fn(medico_id),
            payload=cast("dict[str, Any]", dict(payload)),
        )

    async def adquirir_lock_sweeper(self, ttl_segundos: int = 55) -> bool:
        """Acquire exclusive NX EX distributed lock for queue reconciliation task."""
        acquired = await self._valkey.set(
            SWEEPER_LOCK_KEY, "1", nx=True, ex=ttl_segundos
        )
        return bool(acquired)

    async def liberar_lock_sweeper(self) -> None:
        """Release exclusive queue reconciliation lock."""
        await self._valkey.delete(SWEEPER_LOCK_KEY)

    async def esta_bloqueado_para_reconciliacao(
        self,
        atendimento_id: UUID,
        medico_id: UUID | None,
    ) -> bool:
        """Check ZSET presence and attendance/doctor locks in one pipeline."""
        atend_str = str(atendimento_id)
        async with self._valkey.pipeline(transaction=True) as pipe:
            pipe.zscore(FILA_APTOS_KEY, atend_str)  # pyright: ignore[reportUnknownMemberType]
            pipe.exists(self._k_lock_atendimento(atendimento_id))
            if medico_id is not None:
                pipe.get(self._k_lock_medico(medico_id))
                pipe.get(self._k_lock_consulta_ativa(medico_id))
            results = await pipe.execute()

        if results[0] is not None or bool(results[1]):
            return True
        if medico_id is None:
            return False
        return _lock_matches(results[2], atend_str) or _lock_matches(
            results[3], atend_str
        )


__all__ = [
    "FILA_APTOS_KEY",
    "PLANTAO_MEDICOS_KEY",
    "SWEEPER_LOCK_KEY",
    "ValkeyQueueEngine",
]
