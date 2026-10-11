"""Valkey cache adapter for telemetry dashboard and in-memory test double."""

import json
import time
from typing import Any

from redis.asyncio import Redis

from src.core.valkey import get_valkey_pool
from src.modules.telemetry.application.dtos import PainelTelemetriaDTO
from src.modules.telemetry.application.ports.telemetry_cache_port import (
    TelemetryCachePort,
)


class ValkeyTelemetryCache(TelemetryCachePort):
    """Distributed telemetry dashboard cache backed by Valkey/Redis."""

    def __init__(self, valkey: Redis | None = None) -> None:
        self._valkey = (
            valkey if valkey is not None else Redis(connection_pool=get_valkey_pool())
        )

    def _cache_key(self, organizacao_id: int) -> str:
        return f"telemetry:painel:{organizacao_id}"

    async def obter_painel(self, organizacao_id: int) -> PainelTelemetriaDTO | None:
        key = self._cache_key(organizacao_id)
        raw_val = await self._valkey.get(key)  # pyright: ignore[reportUnknownMemberType]
        if not raw_val:
            return None

        try:
            val_str = (
                raw_val.decode("utf-8") if isinstance(raw_val, bytes) else str(raw_val)
            )
            data: dict[str, Any] = json.loads(val_str)
            return PainelTelemetriaDTO.from_dict(data)
        except Exception:
            return None

    async def salvar_painel(
        self,
        organizacao_id: int,
        painel: PainelTelemetriaDTO,
        ttl_segundos: int = 60,
    ) -> None:
        key = self._cache_key(organizacao_id)
        ttl = max(1, ttl_segundos)
        payload = json.dumps(painel.to_dict())
        await self._valkey.set(key, payload, ex=ttl)  # pyright: ignore[reportUnknownMemberType]

    async def invalidar_painel(self, organizacao_id: int) -> None:
        key = self._cache_key(organizacao_id)
        await self._valkey.delete(key)  # pyright: ignore[reportUnknownMemberType]


class MemoryTelemetryCache(TelemetryCachePort):
    """In-memory telemetry cache implementation for fast unit tests."""

    def __init__(self) -> None:
        self._store: dict[int, tuple[PainelTelemetriaDTO, float]] = {}

    async def obter_painel(self, organizacao_id: int) -> PainelTelemetriaDTO | None:
        entry = self._store.get(organizacao_id)
        if entry is None:
            return None
        painel, expiry = entry
        if time.monotonic() > expiry:
            del self._store[organizacao_id]
            return None
        return painel

    async def salvar_painel(
        self,
        organizacao_id: int,
        painel: PainelTelemetriaDTO,
        ttl_segundos: int = 60,
    ) -> None:
        expiry = time.monotonic() + max(1, ttl_segundos)
        self._store[organizacao_id] = (painel, expiry)

    async def invalidar_painel(self, organizacao_id: int) -> None:
        self._store.pop(organizacao_id, None)
