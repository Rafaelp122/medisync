"""Valkey sliding window rate limiter adapter implementing AuthRateLimiterPort."""

import contextlib
import time
from typing import Any

from redis.asyncio import Redis

from src.core.uuid7 import uuid7
from src.core.valkey import get_valkey_pool
from src.modules.auth.application.dtos import RateLimitResultDTO
from src.modules.auth.application.ports.auth_rate_limiter_port import (
    AuthRateLimiterPort,
)


class ValkeyAuthRateLimiter(AuthRateLimiterPort):
    """Sliding-window rate limiter using Valkey ZSET to prevent brute-force attacks."""

    def __init__(self, client: Redis | None = None) -> None:
        self._client = client

    def _get_client(self) -> Redis:
        if self._client is not None:
            return self._client
        return Redis(connection_pool=get_valkey_pool())

    async def verificar_e_incrementar(
        self,
        chave: str,
        limite: int = 5,
        janela_segundos: int = 900,
    ) -> RateLimitResultDTO:
        """Check sliding window attempt count and record new attempt atomically."""
        client = self._get_client()
        redis_key = f"auth:ratelimit:{chave}"
        now = time.time()
        window_start = now - janela_segundos

        try:
            async with client.pipeline(transaction=True) as pipe:
                await pipe.zremrangebyscore(redis_key, 0, window_start)  # pyright: ignore[reportUnknownMemberType]
                await pipe.zcard(redis_key)  # pyright: ignore[reportUnknownMemberType]
                results: list[Any] = await pipe.execute()  # pyright: ignore[reportUnknownMemberType]

            current_count = int(results[1])
            if current_count >= limite:
                oldest_entries: list[Any] = await client.zrange(  # pyright: ignore[reportUnknownMemberType]
                    redis_key, 0, 0, withscores=True
                )
                retry_after = janela_segundos
                if oldest_entries:
                    oldest_time = float(oldest_entries[0][1])
                    retry_after = max(1, int(oldest_time + janela_segundos - now))
                return RateLimitResultDTO(
                    permitido=False,
                    tentativas_restantes=0,
                    retry_after_segundos=retry_after,
                )

            async with client.pipeline(transaction=True) as pipe:
                member_val = f"{now}:{uuid7()}"
                await pipe.zadd(redis_key, {member_val: now})  # pyright: ignore[reportUnknownMemberType]
                await pipe.expire(redis_key, janela_segundos)  # pyright: ignore[reportUnknownMemberType]
                await pipe.execute()  # pyright: ignore[reportUnknownMemberType]

            tentativas_restantes = max(0, limite - (current_count + 1))
            return RateLimitResultDTO(
                permitido=True,
                tentativas_restantes=tentativas_restantes,
                retry_after_segundos=0,
            )
        except Exception:
            # Resilient fallback: do not break login flow if cache is unreachable
            return RateLimitResultDTO(
                permitido=True,
                tentativas_restantes=max(0, limite - 1),
                retry_after_segundos=0,
            )

    async def resetar(self, chave: str) -> None:
        """Reset attempt counters for the given key upon successful login."""
        client = self._get_client()
        redis_key = f"auth:ratelimit:{chave}"
        with contextlib.suppress(Exception):
            await client.delete(redis_key)  # pyright: ignore[reportUnknownMemberType]


class FakeAuthRateLimiter(AuthRateLimiterPort):
    """In-memory rate limiter for deterministic and fast unit testing."""

    def __init__(self) -> None:
        self._attempts: dict[str, list[float]] = {}

    async def verificar_e_incrementar(
        self,
        chave: str,
        limite: int = 5,
        janela_segundos: int = 900,
    ) -> RateLimitResultDTO:
        now = time.time()
        window_start = now - janela_segundos
        history = [t for t in self._attempts.get(chave, []) if t > window_start]
        self._attempts[chave] = history

        if len(history) >= limite:
            oldest = history[0]
            retry_after = max(1, int(oldest + janela_segundos - now))
            return RateLimitResultDTO(
                permitido=False,
                tentativas_restantes=0,
                retry_after_segundos=retry_after,
            )

        history.append(now)
        self._attempts[chave] = history
        return RateLimitResultDTO(
            permitido=True,
            tentativas_restantes=limite - len(history),
            retry_after_segundos=0,
        )

    async def resetar(self, chave: str) -> None:
        self._attempts.pop(chave, None)
