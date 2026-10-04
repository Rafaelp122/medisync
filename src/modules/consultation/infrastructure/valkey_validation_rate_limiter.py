"""Valkey sliding-window rate limiter for public validation endpoints."""

import contextlib
import time
from typing import Any

from redis.asyncio import Redis

from src.core.uuid7 import uuid7
from src.core.valkey import get_valkey_pool
from src.modules.consultation.application.ports.validation_rate_limiter_port import (
    ValidationRateLimiterPort,
    ValidationRateLimitResult,
)


class ValkeyValidationRateLimiter(ValidationRateLimiterPort):
    """Sliding-window limiter using Valkey ZSET (same pattern as auth)."""

    def __init__(self, client: Redis | None = None) -> None:
        self._client = client

    def _get_client(self) -> Redis:
        if self._client is not None:
            return self._client
        return Redis(connection_pool=get_valkey_pool())

    async def verificar_e_incrementar(
        self,
        chave: str,
        limite: int = 30,
        janela_segundos: int = 60,
    ) -> ValidationRateLimitResult:
        client = self._get_client()
        redis_key = f"validation:ratelimit:{chave}"
        now = time.time()
        window_start = now - janela_segundos
        try:
            async with client.pipeline(transaction=True) as pipe:
                await pipe.zremrangebyscore(redis_key, 0, window_start)  # pyright: ignore[reportUnknownMemberType]
                await pipe.zcard(redis_key)  # pyright: ignore[reportUnknownMemberType]
                results: list[object] = await pipe.execute()  # pyright: ignore[reportUnknownMemberType]
            current_count = int(results[1])  # type: ignore[arg-type]
            if current_count >= limite:
                oldest: list[Any] = await client.zrange(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                    redis_key, 0, 0, withscores=True
                )
                retry_after = janela_segundos
                if oldest:
                    first: Any = oldest[0]
                    if isinstance(first, (list, tuple)) and len(first) == 2:  # pyright: ignore[reportUnknownArgumentType]
                        second: Any = first[1]  # pyright: ignore[reportUnknownVariableType]
                        if isinstance(second, (int, float)):
                            oldest_time = float(second)
                            retry_after = max(
                                1, int(oldest_time + janela_segundos - now)
                            )
                return ValidationRateLimitResult(
                    permitido=False,
                    tentativas_restantes=0,
                    retry_after_segundos=retry_after,
                )
            async with client.pipeline(transaction=True) as pipe:
                member_val = f"{now}:{uuid7()}"
                await pipe.zadd(redis_key, {member_val: now})  # pyright: ignore[reportUnknownMemberType]
                await pipe.expire(redis_key, janela_segundos)  # pyright: ignore[reportUnknownMemberType]
                await pipe.execute()  # pyright: ignore[reportUnknownMemberType]
            return ValidationRateLimitResult(
                permitido=True,
                tentativas_restantes=max(0, limite - (current_count + 1)),
                retry_after_segundos=0,
            )
        except Exception:
            return ValidationRateLimitResult(
                permitido=True,
                tentativas_restantes=max(0, limite - 1),
                retry_after_segundos=0,
            )

    async def resetar(self, chave: str) -> None:
        client = self._get_client()
        with contextlib.suppress(Exception):
            await client.delete(f"validation:ratelimit:{chave}")  # pyright: ignore[reportUnknownMemberType]


class FakeValidationRateLimiter(ValidationRateLimiterPort):
    """In-memory limiter for deterministic unit tests."""

    def __init__(self) -> None:
        self._attempts: dict[str, list[float]] = {}

    async def verificar_e_incrementar(
        self,
        chave: str,
        limite: int = 30,
        janela_segundos: int = 60,
    ) -> ValidationRateLimitResult:
        now = time.time()
        window_start = now - janela_segundos
        history = [t for t in self._attempts.get(chave, []) if t > window_start]
        self._attempts[chave] = history
        if len(history) >= limite:
            oldest = history[0]
            retry_after = max(1, int(oldest + janela_segundos - now))
            return ValidationRateLimitResult(
                permitido=False,
                tentativas_restantes=0,
                retry_after_segundos=retry_after,
            )
        history.append(now)
        self._attempts[chave] = history
        return ValidationRateLimitResult(
            permitido=True,
            tentativas_restantes=limite - len(history),
            retry_after_segundos=0,
        )

    async def resetar(self, chave: str) -> None:
        self._attempts.pop(chave, None)
