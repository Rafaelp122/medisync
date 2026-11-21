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

    _CACHE_KEY = "telemetry:painel"

    def __init__(self, valkey: Redis | None = None) -> None:
        self._valkey = (
            valkey if valkey is not None else Redis(connection_pool=get_valkey_pool())
        )

    async def obter_painel(self) -> PainelTelemetriaDTO | None:
        raw_val = await self._valkey.get(self._CACHE_KEY)  # pyright: ignore[reportUnknownMemberType]
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
        painel: PainelTelemetriaDTO,
        ttl_segundos: int = 60,
    ) -> None:
        ttl = max(1, ttl_segundos)
        payload = json.dumps(painel.to_dict())
        await self._valkey.set(self._CACHE_KEY, payload, ex=ttl)  # pyright: ignore[reportUnknownMemberType]

    async def invalidar_painel(self) -> None:
        await self._valkey.delete(self._CACHE_KEY)  # pyright: ignore[reportUnknownMemberType]


class MemoryTelemetryCache(TelemetryCachePort):
    """In-memory telemetry cache implementation for fast unit tests."""

    def __init__(self) -> None:
        self._entry: tuple[PainelTelemetriaDTO, float] | None = None

    async def obter_painel(self) -> PainelTelemetriaDTO | None:
        if self._entry is None:
            return None
        painel, expiry = self._entry
        if time.monotonic() > expiry:
            self._entry = None
            return None
        return painel

    async def salvar_painel(
        self,
        painel: PainelTelemetriaDTO,
        ttl_segundos: int = 60,
    ) -> None:
        expiry = time.monotonic() + max(1, ttl_segundos)
        self._entry = (painel, expiry)

    async def invalidar_painel(self) -> None:
        self._entry = None
